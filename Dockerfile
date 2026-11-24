FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python deps
COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/base.txt

# Copy project
COPY . .

RUN groupadd --system app && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app \
    && chown -R app:app /app

USER app

EXPOSE 8000
