import threading
import queue
import os
import time
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
    "has_cookies": False
}

OUTPUT_DIR = os.path.abspath("downloads")
COOKIES_PATH = os.path.abspath("cookies.txt")
os.makedirs(OUTPUT_DIR, exist_ok=True)

YOUTUBE_CLIENTS = ["android", "android_vr", "tv_downgraded", "mweb", "web"]


def append_log(msg: str):
    progress["log"].append(msg)
    if len(progress["log"]) > 300:
        progress["log"] = progress["log"][-300:]


def progress_hook(d):
    if d.get("status") == "downloading":
        progress["state"] = "downloading"
        progress["percent"] = (d.get("_percent_str") or "").strip()
        progress["eta"] = d.get("_eta_str") or ""
        progress["speed"] = d.get("_speed_str") or ""
    elif d.get("status") == "finished":
        progress["percent"] = "100%"
        progress["eta"] = "0"
        progress["speed"] = ""
        append_log("✅ تمام شد: " + (progress.get("current_title") or ""))


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

    ydl_opts = {
        "format": fmt,
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(OUTPUT_DIR, "%(title).80s.%(ext)s"),
        "progress_hooks": [progress_hook],
        "nopart": True,
        "continuedl": False,
        "retries": 30,
        "fragment_retries": 30,
        "retry_sleep": 3,
        "restrictfilenames": True,
        "quiet": True,
        "noprogress": True,
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

    return ydl_opts


def download_worker():
    while True:
        task = job_queue.get()
        if task is None:
            break
        try:
            links = task["links"]
            quality = task.get("quality", "360")

            for f in Path(OUTPUT_DIR).glob("*"):
                try:
                    if f.is_file():
                        f.unlink()
                except Exception:
                    pass

            progress.update({
                "state": "downloading",
                "current_index": 0,
                "total": len(links),
                "current_title": "",
                "percent": "",
                "speed": "",
                "eta": "",
                "log": [],
                "files": [],
                "has_cookies": bool(get_cookies_path())
            })

            append_log(f"▶ شروع دانلود {len(links)} ویدیو | کیفیت: {quality}")
            append_log(f"🍪 کوکی: {'فعال' if get_cookies_path() else 'ندارد'}")

            ydl_opts = build_ydl_opts(quality)

            with YoutubeDL(ydl_opts) as ydl:
                for i, ln in enumerate(links, 1):
                    progress["current_index"] = i
                    progress["current_title"] = ln
                    append_log(f"⬇ [{i}/{len(links)}] در حال دانلود...")

                    try:
                        try:
                            info = ydl.extract_info(ln, download=False)
                            title = info.get("title") or ln
                            progress["current_title"] = title
                            append_log(f"   عنوان: {title[:80]}")
                        except Exception as e:
                            append_log(f"   نتوانست عنوان بگیرد: {str(e)[:80]}")

                        ydl.download([ln])

                        time.sleep(0.5)
                        files = sorted(
                            Path(OUTPUT_DIR).glob("*"),
                            key=lambda p: p.stat().st_mtime,
                            reverse=True
                        )
                        for f in files:
                            if f.is_file() and f.suffix.lower() in {".mp4", ".mkv", ".webm", ".m4a", ".mp3"}:
                                already = any(x["name"] == f.name for x in progress["files"])
                                if not already:
                                    progress["files"].append({
                                        "name": f.name,
                                        "size": f.stat().st_size,
                                        "title": progress["current_title"]
                                    })
                                    append_log(f"📥 آماده: {f.name}")
                                    break
                    except Exception as e:
                        append_log(f"❌ خطا: {str(e)[:200]}")

            progress["state"] = "done"
            if progress["files"]:
                append_log("✅ تمام. فایل‌ها را از پایین دانلود کنید.")
            else:
                append_log("⚠️ دانلود تمام شد اما فایلی ساخته نشد.")
        except Exception as e:
            progress["state"] = "error"
            append_log(f"❌ خطای کلی: {e}")
        finally:
            job_queue.task_done()


t = threading.Thread(target=download_worker, daemon=True)
t.start()


@app.route("/")
def index():
    progress["has_cookies"] = bool(get_cookies_path())
    return render_template("index.html")


@app.route("/start", methods=["POST"])
def start():
    data = request.get_json(force=True)
    links = [ln.strip() for ln in data.get("links", "").splitlines() if ln.strip()]
    quality = data.get("quality", "360")

    if not links:
        return jsonify({"ok": False, "msg": "لینکی وارد نشده"}), 400

    if progress["state"] in ("downloading", "queued"):
        return jsonify({"ok": False, "msg": "در حال دانلود است، صبر کنید"}), 400

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
        "has_cookies": bool(get_cookies_path())
    })

    job_queue.put({"links": links, "quality": quality})
    return jsonify({"ok": True})


@app.route("/progress")
def get_progress():
    progress["has_cookies"] = bool(get_cookies_path())
    return jsonify(progress)


@app.route("/upload-cookies", methods=["POST"])
def upload_cookies():
    if "cookies" not in request.files:
        return jsonify({"ok": False, "msg": "فایلی نیست"}), 400
    f = request.files["cookies"]
    content = f.read()
    if len(content) < 50:
        return jsonify({"ok": False, "msg": "فایل خالی یا خیلی کوچک است"}), 400
    with open(COOKIES_PATH, "wb") as out:
        out.write(content)
    progress["has_cookies"] = True
    append_log("🍪 کوکی آپلود شد")
    return jsonify({"ok": True})


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
