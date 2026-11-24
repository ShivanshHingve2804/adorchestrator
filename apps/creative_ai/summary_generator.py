import json

from .extractor import generate_text


def generate_summary(correlations):
    prompt = (
        "Write a concise weekly ad-performance summary from the supplied JSON. "
        "Use only the measurements provided, distinguish correlation from causation, "
        "call out small sample sizes, and do not invent values.\n\n"
        + json.dumps(correlations, sort_keys=True)
    )
    return generate_text(prompt)
