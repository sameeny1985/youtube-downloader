FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=10000

RUN apt-get update && apt-get install -y \
    curl \
    unzip \
    ffmpeg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deno.land/install.sh | sh

ENV PATH="/root/.deno/bin:$PATH"

RUN deno --version

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "echo DENO: && deno --version && echo YTDLP: && yt-dlp --version && exec gunicorn --workers 1 --threads 8 --timeout 0 --bind 0.0.0.0:${PORT} app:app"]
