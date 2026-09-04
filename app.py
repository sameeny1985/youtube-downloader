import threading
import os
import time
import traceback
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory, abort
from yt_dlp import YoutubeDL

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

_lock = threading.Lock()

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
        "retries": 15,
        "fragment_retries": 15,
        "retry_sleep": 2,
        "restrictfilenames": True,
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "extractor_args": {
            "youtube": {"player_client": ["android", "android_vr", "tv_downgraded", "mweb"]}
        },
    }
    cookies = get_cookies_path()
    if cookies:
        opts["cookiefile"] = cookies
    return opts


def run_download(links, quality):
    """این تابع داخل یک Thread جدا اجرا می‌شود"""
    try:
        # پاکسازی فایل‌های قبلی
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
                "message": "شروع دانلود"
            })

        append_log(f"▶ شروع | {len(links)} ویدیو | کیفیت: {quality}")
        append_log(f"🍪 کوکی: {'بله' if get_cookies_path() else 'خیر'}")

        ydl_opts = build_ydl_opts(quality)

        with YoutubeDL(ydl_opts) as ydl:
            for i, ln in enumerate(links, 1):
                with _lock:
                    progress["current_index"] = i
                    progress["current_title"] = ln
                    progress["message"] = f"دانلود {i}/{len(links)}"

                append_log(f"⬇ [{i}/{len(links)}] {ln[:70]}")

                try:
                    info = ydl.extract_info(ln, download=False)
                    title = (info.get("title") or "video")[:80]
                    with _lock:
                        progress["current_title"] = title
                    append_log(f"   📺 {title}")

                    ydl.download([ln])

                    time.sleep(0.3)
                    for f in sorted(Path(OUTPUT_DIR).glob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
                        if f.is_file() and f.suffix.lower() in {".mp4", ".mkv", ".webm", ".m4a", ".mp3"}:
                            with _lock:
                                if not any(x["name"] == f.name for x in progress["files"]):
                                    progress["files"].append({
                                        "name": f.name,
                                        "size": f.stat().st_size,
                                        "title": title
                                    })
                                    append_log(f"📥 آماده: {f.name}")
                                    break
                except Exception as e:
                    append_log(f"❌ {str(e)[:200]}")

        with _lock:
            progress["state"] = "done"
            progress["message"] = "تمام"
        if progress["files"]:
            append_log("✅ موفق — فایل را از پایین دانلود کنید")
        else:
            append_log("⚠️ تمام شد ولی فایلی ساخته نشد")

    except Exception as e:
        with _lock:
            progress["state"] = "error"
            progress["message"] = "خطا"
        append_log(f"❌ خطای کلی: {e}")
        append_log(traceback.format_exc()[-200:])


@app.route("/")
def index():
    progress["has_cookies"] = bool(get_cookies_path())
    return render_template("index.html")


@app.route("/api/ping")
def ping():
    return jsonify({
        "ok": True,
        "state": progress["state"],
        "has_cookies": bool(get_cookies_path()),
        "files": len(progress.get("files") or [])
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

        # اگر گیر کرده بود، اجباراً ریست کن
        if progress["state"] in ("downloading", "queued"):
            # اجازه شروع جدید — thread قبلی اگر گیر کرده باشد کاری از دستمان برنمی‌آید
            # ولی state را ریست می‌کنیم تا کاربر معطل نشود
            pass

        with _lock:
            progress["state"] = "queued"
            progress["message"] = "در حال شروع..."
            progress["log"] = ["درخواست دریافت شد، در حال شروع thread..."]
            progress["files"] = []
            progress["has_cookies"] = bool(get_cookies_path())

        # هر بار یک thread جدید — دیگر به صف وابسته نیست
        t = threading.Thread(target=run_download, args=(links, quality), daemon=True)
        t.start()

        return jsonify({"ok": True, "msg": f"دانلود {len(links)} ویدیو شروع شد"})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/reset", methods=["POST"])
def reset():
    """اگر گیر کرد، state را ریست کن"""
    with _lock:
        progress.update({
            "state": "idle",
            "current_index": 0,
            "total": 0,
            "current_title": "",
            "percent": "",
            "speed": "",
            "eta": "",
            "message": "",
            "log": ["ریست شد"],
            "files": progress.get("files") or [],
            "has_cookies": bool(get_cookies_path())
        })
    return jsonify({"ok": True, "msg": "ریست شد"})


@app.route("/progress")
def get_progress():
    with _lock:
        data = dict(progress)
    data["has_cookies"] = bool(get_cookies_path())
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
