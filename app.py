import threading
import queue
import os
import time
import traceback
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory, abort
from yt_dlp import YoutubeDL

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

job_queue = queue.Queue()

progress = {
    "state": "idle",
    "current_index": 0,
    "total": 0,
    "current_title": "",
    "percent": "",
    "speed": "",
    "eta": "",
    "log": [],
    "files": [],
    "has_cookies": False,
    "message": ""
}

OUTPUT_DIR = os.path.abspath("downloads")
COOKIES_PATH = os.path.abspath("cookies.txt")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# قفل برای جلوگیری از تداخل
_lock = threading.Lock()


def append_log(msg: str):
    with _lock:
        progress["log"].append(msg)
        if len(progress["log"]) > 300:
            progress["log"] = progress["log"][-300:]


def progress_hook(d):
    if d.get("status") == "downloading":
        with _lock:
            progress["state"] = "downloading"
            progress["percent"] = (d.get("_percent_str") or "").strip()
            progress["eta"] = d.get("_eta_str") or ""
            progress["speed"] = d.get("_speed_str") or ""
    elif d.get("status") == "finished":
        with _lock:
            progress["percent"] = "100%"
            progress["eta"] = "0"
            progress["speed"] = ""
        append_log("✅ فایل ذخیره شد")


def get_cookies_path():
    if os.path.isfile(COOKIES_PATH) and os.path.getsize(COOKIES_PATH) > 50:
        return COOKIES_PATH
    return None


def build_ydl_opts(quality: str):
    if quality == "240":
        fmt = "best[height<=240]/worst"
    elif quality == "360":
        fmt = "best[height<=360]/best"
    else:
        fmt = "best"

    opts = {
        "format": fmt,
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(OUTPUT_DIR, "%(title).80s.%(ext)s"),
        "progress_hooks": [progress_hook],
        "nopart": True,
        "continuedl": False,
        "retries": 20,
        "fragment_retries": 20,
        "retry_sleep": 3,
        "restrictfilenames": True,
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "extractor_args": {
            "youtube": {"player_client": ["android", "android_vr", "tv_downgraded", "mweb"]}
        },
    }
    cookies = get_cookies_path()
    if cookies:
        opts["cookiefile"] = cookies
    return opts


def download_worker():
    while True:
        task = job_queue.get()
        if task is None:
            break
        try:
            links = task["links"]
            quality = task.get("quality", "360")

            # پاکسازی
            for f in Path(OUTPUT_DIR).glob("*"):
                try:
                    f.unlink()
                except Exception:
                    pass

            with _lock:
                progress.update({
                    "state": "downloading",
                    "current_index": 0,
                    "total": len(links),
                    "current_title": "",
                    "percent": "0%",
                    "speed": "",
                    "eta": "",
                    "log": [],
                    "files": [],
                    "has_cookies": bool(get_cookies_path()),
                    "message": "در حال دانلود..."
                })

            append_log(f"▶ شروع | تعداد: {len(links)} | کیفیت: {quality}")
            append_log(f"🍪 کوکی: {'بله' if get_cookies_path() else 'خیر'}")

            ydl_opts = build_ydl_opts(quality)

            with YoutubeDL(ydl_opts) as ydl:
                for i, ln in enumerate(links, 1):
                    with _lock:
                        progress["current_index"] = i
                        progress["current_title"] = ln
                        progress["message"] = f"دانلود {i} از {len(links)}"

                    append_log(f"⬇ [{i}/{len(links)}] {ln[:60]}")

                    try:
                        info = ydl.extract_info(ln, download=False)
                        title = (info.get("title") or "video")[:80]
                        with _lock:
                            progress["current_title"] = title
                        append_log(f"   📺 {title}")

                        ydl.download([ln])

                        time.sleep(0.4)
                        found = False
                        for f in sorted(Path(OUTPUT_DIR).glob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
                            if f.is_file() and f.suffix.lower() in {".mp4", ".mkv", ".webm", ".m4a", ".mp3"}:
                                with _lock:
                                    if not any(x["name"] == f.name for x in progress["files"]):
                                        progress["files"].append({
                                            "name": f.name,
                                            "size": f.stat().st_size,
                                            "title": title
                                        })
                                        found = True
                                        append_log(f"📥 آماده: {f.name} ({f.stat().st_size // 1024} KB)")
                                        break
                        if not found:
                            append_log("⚠️ فایل روی دیسک پیدا نشد")
                    except Exception as e:
                        append_log(f"❌ {str(e)[:180]}")

            with _lock:
                progress["state"] = "done"
                progress["message"] = "تمام شد"
                if progress["files"]:
                    append_log("✅ موفق — از بخش پایین دانلود کنید")
                else:
                    append_log("⚠️ تمام شد ولی فایلی ساخته نشد")
        except Exception as e:
            with _lock:
                progress["state"] = "error"
                progress["message"] = "خطا"
            append_log(f"❌ خطای کلی: {e}")
            append_log(traceback.format_exc()[-300:])
        finally:
            job_queue.task_done()


# شروع worker
_worker = threading.Thread(target=download_worker, daemon=True, name="dl-worker")
_worker.start()


def ensure_worker():
    global _worker
    if not _worker.is_alive():
        _worker = threading.Thread(target=download_worker, daemon=True, name="dl-worker")
        _worker.start()
        append_log("🔄 worker دوباره راه‌اندازی شد")


@app.route("/")
def index():
    progress["has_cookies"] = bool(get_cookies_path())
    return render_template("index.html")


@app.route("/api/ping")
def ping():
    """برای تست زنده بودن سرور"""
    return jsonify({
        "ok": True,
        "worker_alive": _worker.is_alive(),
        "queue_size": job_queue.qsize(),
        "state": progress["state"],
        "has_cookies": bool(get_cookies_path())
    })


@app.route("/start", methods=["POST"])
def start():
    try:
        data = request.get_json(force=True, silent=True) or {}
        raw = data.get("links", "")
        links = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        quality = data.get("quality", "360")

        if not links:
            return jsonify({"ok": False, "msg": "لینکی وارد نشده"}), 400

        ensure_worker()

        if progress["state"] in ("downloading", "queued"):
            return jsonify({"ok": False, "msg": "یک دانلود در حال اجراست. صبر کنید."}), 400

        with _lock:
            progress.update({
                "state": "queued",
                "current_index": 0,
                "total": len(links),
                "current_title": "",
                "percent": "",
                "speed": "",
                "eta": "",
                "log": ["در صف قرار گرفت..."],
                "files": [],
                "has_cookies": bool(get_cookies_path()),
                "message": "در صف..."
            })

        job_queue.put({"links": links, "quality": quality})
        return jsonify({"ok": True, "msg": f"{len(links)} لینک در صف قرار گرفت", "worker": _worker.is_alive()})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/progress")
def get_progress():
    with _lock:
        data = dict(progress)
    data["has_cookies"] = bool(get_cookies_path())
    data["worker_alive"] = _worker.is_alive()
    return jsonify(data)


@app.route("/upload-cookies", methods=["POST"])
def upload_cookies():
    if "cookies" not in request.files:
        return jsonify({"ok": False, "msg": "فایلی ارسال نشد"}), 400
    f = request.files["cookies"]
    content = f.read()
    if len(content) < 50:
        return jsonify({"ok": False, "msg": "فایل خیلی کوچک است"}), 400
    with open(COOKIES_PATH, "wb") as out:
        out.write(content)
    progress["has_cookies"] = True
    append_log("🍪 کوکی ذخیره شد")
    return jsonify({"ok": True, "msg": "کوکی ذخیره شد"})


@app.route("/delete-cookies", methods=["POST"])
def delete_cookies():
    try:
        if os.path.isfile(COOKIES_PATH):
            os.remove(COOKIES_PATH)
        progress["has_cookies"] = False
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/download/<path:filename>")
def download_file(filename):
    safe = Path(OUTPUT_DIR) / filename
    if not safe.exists() or not safe.is_file():
        abort(404)
    if not str(safe.resolve()).startswith(str(Path(OUTPUT_DIR).resolve())):
        abort(403)
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True, download_name=filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
