FROM python:3.12-slim

# نصب ffmpeg و ابزارهای لازم
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# پوشه دانلود
RUN mkdir -p /app/downloads

# پورت پیش‌فرض Render
ENV PORT=10000
EXPOSE 10000

# اجرای با gunicorn (یک worker کافی است چون از thread استفاده می‌کنیم)
CMD gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 300 app:app
