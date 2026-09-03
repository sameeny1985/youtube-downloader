import os
from flask import Flask, render_template, request, jsonify
from yt_dlp import YoutubeDL

app = Flask(__name__)

def analyze_links(raw_links):
    links = [ln.strip() for ln in raw_links.splitlines() if ln.strip()]
    results = []
    
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }
    
    with YoutubeDL(ydl_opts) as ydl:
        for ln in links:
            try:
                info = ydl.extract_info(ln, download=False)
                
                # پیدا کردن بهترین لینک دانلود مستقیم ویدیو/صدا
                formats = info.get("formats", [])
                direct_url = ""
                
                # فیلتر برای گرفتن لینک مستقیم mp4
                for f in formats:
                    if f.get("ext") == "mp4" and f.get("url"):
                        direct_url = f.get("url")
                        # اگر فرمت ترکیبی نبود و صدا داشت ترجیح داده می‌شود
                        if f.get("acodec") != "none" and f.get("vcodec") != "none":
                            break

                # اگر لینک مستقیم پیدا نشد، از url اصلی یا webpage استفاده کن
                if not direct_url:
                    direct_url = info.get("url", ln)

                results.append({
                    "title": info.get("title", "بدون عنوان"),
                    "thumbnail": info.get("thumbnail", ""),
                    "url": info.get("webpage_url", ln),
                    "direct_download_url": direct_url,
                    "duration": info.get("duration_string", ""),
                    "id": info.get("id", "")
                })
            except Exception as e:
                results.append({
                    "title": f"خطا در خواندن: {ln} ({str(e)})",
                    "thumbnail": "",
                    "url": ln,
                    "direct_download_url": "",
                    "id": ""
                })
    return results

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json(force=True)
    raw_links = data.get("links", "")
    items = analyze_links(raw_links)
    return jsonify({"items": items})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
