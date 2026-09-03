FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DEBIAN_FRONTEND=noninteractive

# نصب ابزارهای لازم
RUN apt-get update && apt-get install -y \
    curl \
    unzip \
    ffmpeg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# نصب Deno
RUN curl -fsSL https://deno.land/install.sh | sh

ENV PATH="/root/.deno/bin:${PATH}"

# بررسی Deno
RUN deno --version

WORKDIR /app

# نصب Python dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "yt-dlp[default]" \
    && pip install --no-cache-dir -r requirements.txt

# فایل‌های پروژه
COPY . .

# Render از PORT استفاده می‌کند
ENV PORT=10000

EXPOSE 10000

CMD ["sh", "-c", "deno --version && yt-dlp --version && gunicorn --workers 1 --threads 8 --timeout 0 --bind 0.0.0.0:${PORT} app:app"]
