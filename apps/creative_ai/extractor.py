"""Provider-configurable creative feature extraction with bounded media downloads."""
import base64
import ipaddress
import json
import imageio_ffmpeg
import socket
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx
from django.conf import settings
from PIL import Image


FEATURE_NAMES = ("hook_style", "text_density", "dominant_tone", "pacing", "cta_type")
MAX_MEDIA_BYTES = 10 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024


def _validate_public_url(media_url):
    parsed = urlparse(media_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Creative media URL must use HTTP or HTTPS.")
    if parsed.username or parsed.password:
        raise ValueError("Credentials are not permitted in creative media URLs.")
    try:
        resolved = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))}
    except socket.gaierror as exc:
        raise ValueError("Creative media host could not be resolved.") from exc
    if not resolved or any(not ipaddress.ip_address(address).is_global for address in resolved):
        raise ValueError("Creative media URL must resolve to a public address.")

    return parsed


def _download_media(media_url, media_type):
    parsed = _validate_public_url(media_url)
    max_size = MAX_MEDIA_BYTES if media_type == "IMAGE" else MAX_VIDEO_BYTES
    expected_type = "image/" if media_type == "IMAGE" else "video/"
    chunks = []
    total = 0
    with httpx.stream("GET", media_url, timeout=settings.AI_REQUEST_TIMEOUT, follow_redirects=False) as response:
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if not content_type.startswith(expected_type):
            raise ValueError(f"Creative media URL did not return {media_type.lower()} media.")
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > max_size:
                raise ValueError(f"Creative {media_type.lower()} exceeds the {max_size // (1024 * 1024)} MiB analysis limit.")
            chunks.append(chunk)
    payload = b"".join(chunks)
    if media_type == "VIDEO":
        return _extract_video_frames(payload, parsed.path)
    try:
        with Image.open(BytesIO(payload)) as image:
            image.verify()
    except Exception as exc:
        raise ValueError("Creative image could not be decoded.") from exc
    return [(content_type, payload)]


def _extract_video_frames(payload, source_path):
    """Sample up to five frames from a bounded video using the system ffmpeg binary."""
    suffix = Path(source_path).suffix.lower()
    if suffix not in {".mp4", ".mov", ".webm", ".m4v"}:
        suffix = ".mp4"
    try:
        with tempfile.TemporaryDirectory(prefix="creative-video-") as folder:
            source = Path(folder) / f"source{suffix}"
            source.write_bytes(payload)
            output = Path(folder) / "frame-%02d.jpg"
            subprocess.run(
                [imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(source), "-vf", "fps=1/3,scale=640:-2", "-frames:v", "5", str(output)],
                check=True,
                capture_output=True,
                timeout=30,
            )
            frames = sorted(Path(folder).glob("frame-*.jpg"))
            if not frames:
                raise ValueError("No video frames could be sampled.")
            result = []
            for frame in frames:
                data = frame.read_bytes()
                with Image.open(BytesIO(data)) as image:
                    image.verify()
                result.append(("image/jpeg", data))
            return result
    except (FileNotFoundError, RuntimeError) as exc:
        raise RuntimeError("The bundled ffmpeg binary is required to analyze video creatives.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Video frame extraction timed out.") from exc
    except subprocess.CalledProcessError as exc:
        raise ValueError("Video could not be decoded for analysis.") from exc


def _json_object(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("AI provider returned invalid JSON.")
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("AI provider must return a JSON object.")
    return value


def _vision_prompt():
    fields = ", ".join(FEATURE_NAMES)
    return (
        "Analyze this advertisement image or sampled video frames. Return only a JSON object with exactly these string fields: "
        f"{fields}. Use concise descriptive values, do not infer performance, and do not include commentary."
    )


def _provider_content(provider, model, prompt, image=None):
    base_url = settings.AI_BASE_URL.rstrip("/")
    headers = {"Authorization": f"Bearer {settings.AI_API_KEY}"} if settings.AI_API_KEY else {}
    timeout = settings.AI_REQUEST_TIMEOUT
    if provider == "ollama":
        body = {"model": model, "prompt": prompt, "stream": False}
        if image:
            body["images"] = [base64.b64encode(frame[1]).decode("ascii") for frame in image]
        response = httpx.post(f"{base_url}/api/generate", json=body, timeout=timeout)
        response.raise_for_status()
        return response.json()["response"]
    if provider == "openai":
        content = [{"type": "text", "text": prompt}]
        if image:
            for media_type, payload in image:
                content.append({"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{base64.b64encode(payload).decode('ascii')}"}})
        response = httpx.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json={"model": model, "messages": [{"role": "user", "content": content}], "temperature": 0},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    if provider == "gemini":
        parts = [{"text": prompt}]
        if image:
            parts.extend({"inline_data": {"mime_type": media_type, "data": base64.b64encode(payload).decode("ascii")}} for media_type, payload in image)
        response = httpx.post(
            f"{base_url}/models/{quote(model, safe='')}:generateContent",
            headers={"x-goog-api-key": settings.AI_API_KEY} if settings.AI_API_KEY else {},
            json={"contents": [{"parts": parts}], "generationConfig": {"responseMimeType": "application/json"}},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    raise ValueError(f"Unsupported AI_PROVIDER: {provider}")


def _configured_model(vision=True):
    model = settings.AI_VISION_MODEL if vision else settings.AI_TEXT_MODEL
    if not model:
        key = "AI_VISION_MODEL" if vision else "AI_TEXT_MODEL"
        raise RuntimeError(f"Set {key} to the model identifier supported by the configured provider.")
    return model


def extract_features(media_url, media_type):
    if media_type not in {"IMAGE", "VIDEO"}:
        raise ValueError("Feature extraction supports image and video creatives only.")
    image = _download_media(media_url, media_type)
    provider = settings.AI_PROVIDER.lower()
    model = _configured_model(vision=True)
    parsed = _json_object(_provider_content(provider, model, _vision_prompt(), image=image))
    features = {}
    for name in FEATURE_NAMES:
        value = parsed.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"AI response is missing the string feature '{name}'.")
        features[name] = value.strip()[:255]
    return features


def generate_text(prompt):
    provider = settings.AI_PROVIDER.lower()
    model = _configured_model(vision=False)
    text = _provider_content(provider, model, prompt)
    if not isinstance(text, str) or not text.strip():
        raise ValueError("AI provider returned an empty summary.")
    return text.strip()
