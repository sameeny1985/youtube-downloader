import threading
import queue
import os
import time
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory, abort
from yt_dlp import YoutubeDL
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # حداکثر ۲ مگابایت برای کوکی

job_queue = queue.Queue()

# وضعیت کلی دانلود (برای استفاده شخصی مناسب است)
progress = {
    "state": "idle",          # idle | analyzing | queued | downloading | done | error
    "current_index": 0,
    "total": 0,
    "current_title": "",
    "percent": "",
    "speed": "",
    "eta": "",
    "filename": "",
    "log": [],
    "files": [],
    "has_cookies": False
}

OUTPUT_DIR = os.path.abspath("downloads")
COOKIES_PATH = os.path.abspath("cookies.txt")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# کلاینت‌هایی که فعلاً روی IPهای ابری بهتر کار می‌کنند
YOUTUBE_CLIENTS = ["android", "android_vr", "tv_downgraded", "mweb"]


def append_log(msg: str):
    progress["log"].append(msg)
    if len(progress["log"]) > 500:
        progress["log"] = progress["log"][-500:]


def progress_hook(d):
    if d.get("status") == "downloading":
        progress["state"] = "downloading"
        progress["percent"] = (d.get("_percent_str") or "").strip()
        progress["eta"] = d.get("_eta_str") or ""
        progress["speed"] = d.get("_speed_str") or ""
        progress["filename"] = d.get("filename") or ""
    elif d.get("status") == "finished":
        progress["percent"] = "100%"
        progress["eta"] = "0"
        progress["speed"] = ""
        title = progress.get("current_title") or ""
        append_log("✅ Finished: " + title)


def get_cookies_path():
    """اگر فایل کوکی وجود داشته باشد مسیرش را برمی‌گرداند"""
    if os.path.isfile(COOKIES_PATH) and os.path.getsize(COOKIES_PATH) > 50:
        return COOKIES_PATH
    return None


def build_ydl_opts(quality: str, ffmpeg_location: str | None = None):
    """
    فرمت‌ها انعطاف‌پذیرتر شدند تا روی کلاینت‌های مختلف کار کنند:
    - 240p : بهترین ≤ ۲۴۰ یا فallback
    - 360p : بهترین ≤ ۳۶۰ یا فallback
    - best  : بهترین کیفیت موجود
    """
    if quality == "240":
        # اول سعی می‌کند ویدیو+صدا جدا، بعد فرمت‌های آماده
        fmt = "bestvideo[height<=240]+bestaudio/best[height<=240]/worst"
    elif quality == "360":
        fmt = "bestvideo[height<=360]+bestaudio/best[height<=360]/18/best"
    else:
        fmt = "bestvideo+bestaudio/best"

    ydl_opts = {
        "format": fmt,
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(OUTPUT_DIR, "%(title)s.%(ext)s"),
        "progress_hooks": [progress_hook],
        "nopart": True,
        "continuedl": False,
        "retries": 50,
        "fragment_retries": 50,
        "retry_sleep": 5,
        "restrictfilenames": True,
        "quiet": True,
        "noprogress": True,
        "extractor_args": {
            "youtube": {
                "player_client": YOUTUBE_CLIENTS,
            }
        },
    }

    cookies = get_cookies_path()
    if cookies:
        ydl_opts["cookiefile"] = cookies

    if ffmpeg_location:
        ydl_opts["ffmpeg_location"] = ffmpeg_location

    return ydl_opts


def analyze_links(raw_links: str):
    links = [ln.strip() for ln in raw_links.splitlines() if ln.strip()]
    results = []
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {
            "youtube": {
                "player_client": YOUTUBE_CLIENTS,
            }
        },
    }
    cookies = get_cookies_path()
    if cookies:
        ydl_opts["cookiefile"] = cookies

    with YoutubeDL(ydl_opts) as ydl:
        for ln in links:
            try:
                info = ydl.extract_info(ln, download=False)
                results.append({
                    "title": info.get("title", "بدون عنوان"),
                    "thumbnail": info.get("thumbnail", ""),
                    "url": info.get("webpage_url", ln),
                    "id": info.get("id", "")
                })
            except Exception as e:
                err = str(e)
                if "Sign in to confirm" in err or "not a bot" in err:
                    if cookies:
                        short = "هنوز بلاک است — کوکی منقضی شده یا ناکافی است"
                    else:
                        short = "یوتیوب این IP را بلاک کرده (ربات تشخیص داده) — کوکی آپلود کنید"
                else:
                    short = err[:140]
                results.append({
                    "title": f"خطا: {short}",
                    "thumbnail": "",
                    "url": ln,
                    "id": ""
                })
    return results


def download_worker():
    while True:
        task = job_queue.get()
        if task is None:
            break
        try:
            links = task["links"]
            quality = task.get("quality", "360")
            ffmpeg_location = task.get("ffmpeg") or None

            progress.update({
                "state": "downloading",
                "current_index": 0,
                "total": len(links),
                "current_title": "",
                "percent": "",
                "speed": "",
                "eta": "",
                "filename": "",
                "files": []
            })
            cookies = get_cookies_path()
            append_log(f"▶ شروع دانلود {len(links)} مورد... کیفیت: {quality}")
            append_log(f"🍪 کوکی: {'فعال' if cookies else 'ندارد'}")

            ydl_opts = build_ydl_opts(quality, ffmpeg_location)

            with YoutubeDL(ydl_opts) as ydl:
                for i, ln in enumerate(links, 1):
                    progress["current_index"] = i
                    try:
                        info = ydl.extract_info(ln, download=False)
                        progress["current_title"] = info.get("title", ln)
                    except Exception:
                        progress["current_title"] = ln

                    append_log(f"⬇ {i}/{len(links)}: {progress['current_title']}")

                    try:
                        ydl.download([ln])
                        time.sleep(0.3)
                        files_in_dir = sorted(
                            Path(OUTPUT_DIR).glob("*"),
                            key=lambda p: p.stat().st_mtime,
                            reverse=True
                        )
                        for f in files_in_dir:
                            if f.is_file() and f.suffix.lower() in {".mp4", ".mkv", ".webm", ".m4a"}:
                                already = any(item["name"] == f.name for item in progress["files"])
                                if not already:
                                    progress["files"].append({
                                        "name": f.name,
                                        "size": f.stat().st_size,
                                        "title": progress["current_title"]
                                    })
                                    append_log(f"📥 آماده دانلود کاربر: {f.name}")
                                    break
                    except Exception as e:
                        append_log(f"❌ خطا در دانلود: {ln} -> {e}")
                        progress["state"] = "error"

            progress["state"] = "done"
            append_log("✅ همه دانلودها تمام شد. از بخش «فایل‌های آماده» دانلود کنید.")
        except Exception as e:
            progress["state"] = "error"
            append_log(f"❌ خطای عمومی: {e}")
        finally:
            job_queue.task_done()


# شروع worker در پس‌زمینه
t = threading.Thread(target=download_worker, daemon=True)
t.start()


@app.route("/")
def index():
    progress["has_cookies"] = bool(get_cookies_path())
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json(force=True)
    raw_links = data.get("links", "")
    progress["state"] = "analyzing"
    progress["has_cookies"] = bool(get_cookies_path())
    items = analyze_links(raw_links)
    progress["state"] = "idle"
    return jsonify({"items": items, "has_cookies": progress["has_cookies"]})


@app.route("/start", methods=["POST"])
def start():
    data = request.get_json(force=True)
    links = [ln.strip() for ln in data.get("links", "").splitlines() if ln.strip()]
    quality = data.get("quality", "360")
    ffmpeg_loc = data.get("ffmpeg", "") or None

    if not links:
        return jsonify({"ok": False, "msg": "هیچ لینکی وارد نشده"}), 400

    # پاک کردن فایل‌های قدیمی
    try:
        for f in Path(OUTPUT_DIR).glob("*"):
            if f.is_file():
                f.unlink(missing_ok=True)
    except Exception:
        pass

    progress.update({
        "state": "queued",
        "current_index": 0,
        "total": len(links),
        "current_title": "",
        "percent": "",
        "speed": "",
        "eta": "",
        "filename": "",
        "log": [],
        "files": [],
        "has_cookies": bool(get_cookies_path())
    })

    job_queue.put({
        "links": links,
        "quality": quality,
        "ffmpeg": ffmpeg_loc
    })
    return jsonify({"ok": True, "msg": "در صف دانلود قرار گرفت"})


@app.route("/progress")
def get_progress():
    progress["has_cookies"] = bool(get_cookies_path())
    return jsonify(progress)


@app.route("/upload-cookies", methods=["POST"])
def upload_cookies():
    """آپلود فایل cookies.txt"""
    if "cookies" not in request.files:
        return jsonify({"ok": False, "msg": "فایلی ارسال نشده"}), 400

    f = request.files["cookies"]
    if not f.filename:
        return jsonify({"ok": False, "msg": "نام فایل خالی است"}), 400

    # ذخیره موقت و بررسی ساده
    content = f.read()
    if len(content) < 50:
        return jsonify({"ok": False, "msg": "فایل کوکی خیلی کوچک یا خالی است"}), 400

    text = content.decode("utf-8", errors="ignore")
    # بررسی خیلی ساده که شبیه کوکی باشد
    if "youtube" not in text.lower() and ".youtube.com" not in text.lower() and "# Netscape" not in text:
        # بعضی extensionها فرمت متفاوت دارند، پس فقط هشدار می‌دهیم نه رد کامل
        pass

    with open(COOKIES_PATH, "wb") as out:
        out.write(content)

    progress["has_cookies"] = True
    append_log("🍪 فایل کوکی با موفقیت آپلود شد")
    return jsonify({"ok": True, "msg": "کوکی با موفقیت ذخیره شد"})


@app.route("/delete-cookies", methods=["POST"])
def delete_cookies():
    try:
        if os.path.isfile(COOKIES_PATH):
            os.remove(COOKIES_PATH)
        progress["has_cookies"] = False
        append_log("🍪 فایل کوکی حذف شد")
        return jsonify({"ok": True, "msg": "کوکی حذف شد"})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/download/<path:filename>")
def download_file(filename):
    safe_path = Path(OUTPUT_DIR) / filename
    if not safe_path.exists() or not safe_path.is_file():
        abort(404)
    if not str(safe_path.resolve()).startswith(str(Path(OUTPUT_DIR).resolve())):
        abort(403)
    return send_from_directory(
        OUTPUT_DIR,
        filename,
        as_attachment=True,
        download_name=filename
    )


@app.route("/files")
def list_files():
    files = []
    for f in sorted(Path(OUTPUT_DIR).glob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.is_file():
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "mtime": f.stat().st_mtime
            })
    return jsonify({"files": files})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
