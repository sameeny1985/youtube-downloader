import threading, queue, os
from flask import Flask, render_template, request, jsonify, send_file
from yt_dlp import YoutubeDL

app = Flask(__name__)

job_queue = queue.Queue()
progress = {
    "state": "idle",          # idle | analyzing | queued | downloading | done | error
    "current_index": 0,
    "total": 0,
    "current_title": "",
    "percent": "",
    "speed": "",
    "eta": "",
    "filename": "",
    "log": []
}

OUTPUT_DIR = os.path.abspath("downloads")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def append_log(msg):
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
        append_log(
            "✅ Finished: " +
            (progress.get("current_title") or "")
        )


def build_ydl_opts(quality, ffmpeg_location):

    # 240p: 133+140 (نیاز به ffmpeg برای ادغام)
    # 360p: itag 18 (تک‌فایله، همیشه صدا دارد)
    # best : bestvideo+bestaudio (بهترین کیفیت، حجم بیشتر)

    if quality == "240":
        fmt = "133+140"

    elif quality == "360":
        fmt = "18"

    else:
        fmt = "bestvideo+bestaudio"

    ydl_opts = {
        "format": fmt,
        "merge_output_format": "mp4",

        "outtmpl": os.path.join(
            OUTPUT_DIR,
            "%(title)s.%(ext)s"
        ),

        "progress_hooks": [progress_hook],

        "nopart": True,         # فایل .part نسازد
        "continuedl": False,    # همیشه از صفر شروع کن
        "retries": 50,
        "fragment_retries": 50,
        "retry_sleep": 5,

        "restrictfilenames": True,

        "quiet": True,
        "noprogress": True,
    }

    if ffmpeg_location:
        ydl_opts["ffmpeg_location"] = ffmpeg_location

    return ydl_opts


def analyze_links(raw_links):

    links = [
        ln.strip()
        for ln in raw_links.splitlines()
        if ln.strip()
    ]

    results = []

    ydl_opts = {
        "quiet": True
    }

    with YoutubeDL(ydl_opts) as ydl:

        for ln in links:

            try:

                info = ydl.extract_info(
                    ln,
                    download=False
                )

                results.append({
                    "title": info.get(
                        "title",
                        "بدون عنوان"
                    ),

                    "thumbnail": info.get(
                        "thumbnail",
                        ""
                    ),

                    "url": info.get(
                        "webpage_url",
                        ln
                    ),

                    "id": info.get(
                        "id",
                        ""
                    )
                })

            except Exception as e:

                results.append({
                    "title": f"خطا در خواندن: {ln}",
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

            quality = task.get(
                "quality",
                "360"
            )

            ffmpeg_location = (
                task.get("ffmpeg")
                or None
            )

            progress.update({

                "state": "downloading",

                "current_index": 0,

                "total": len(links),

                "current_title": "",

                "percent": "",

                "speed": "",

                "eta": "",

                "filename": ""

            })

            append_log(
                f"▶ شروع دانلود {len(links)} مورد... "
                f"کیفیت: {quality}"
            )

            ydl_opts = build_ydl_opts(
                quality,
                ffmpeg_location
            )

            with YoutubeDL(ydl_opts) as ydl:

                for i, ln in enumerate(
                    links,
                    1
                ):

                    progress[
                        "current_index"
                    ] = i

                    try:

                        info = ydl.extract_info(
                            ln,
                            download=False
                        )

                        progress[
                            "current_title"
                        ] = info.get(
                            "title",
                            ln
                        )

                    except:

                        progress[
                            "current_title"
                        ] = ln

                    append_log(
                        f"⬇ {i}/{len(links)}: "
                        f"{progress['current_title']}"
                    )

                    try:

                        ydl.download([ln])

                    except Exception as e:

                        append_log(
                            f"❌ خطا در دانلود: "
                            f"{ln} -> {e}"
                        )

                        progress[
                            "state"
                        ] = "error"

            progress[
                "state"
            ] = "done"

            append_log(
                "✅ همه دانلودها تمام شد."
            )

        except Exception as e:

            progress[
                "state"
            ] = "error"

            append_log(
                f"❌ خطای عمومی: {e}"
            )

        finally:

            job_queue.task_done()


t = threading.Thread(
    target=download_worker,
    daemon=True
)

t.start()


@app.route("/")
def index():

    return render_template(
        "index.html"
    )


@app.route(
    "/analyze",
    methods=["POST"]
)
def analyze():

    data = request.get_json(
        force=True
    )

    raw_links = data.get(
        "links",
        ""
    )

    progress[
        "state"
    ] = "analyzing"

    items = analyze_links(
        raw_links
    )

    progress[
        "state"
    ] = "idle"

    return jsonify({
        "items": items
    })


@app.route(
    "/start",
    methods=["POST"]
)
def start():

    data = request.get_json(
        force=True
    )

    links = [
        ln.strip()
        for ln in data.get(
            "links",
            ""
        ).splitlines()
        if ln.strip()
    ]

    quality = data.get(
        "quality",
        "360"
    )

    ffmpeg_loc = data.get(
        "ffmpeg",
        ""
    )

    if not links:

        return jsonify({
            "ok": False,
            "msg": "هیچ لینکی وارد نشده"
        }), 400

    progress.update({

        "state": "queued",

        "current_index": 0,

        "total": len(links),

        "current_title": "",

        "percent": "",

        "speed": "",

        "eta": "",

        "filename": "",

        "log": []

    })

    job_queue.put({

        "links": links,

        "quality": quality,

        "ffmpeg": ffmpeg_loc

    })

    return jsonify({
        "ok": True,
        "msg": "در صف دانلود قرار گرفت"
    })


@app.route("/progress")
def get_progress():

    return jsonify(
        progress
    )


# ارسال فایل دانلودشده به مرورگر کاربر
@app.route("/download")
def download_file():

    filename = request.args.get(
        "filename",
        ""
    ).strip()

    if not filename:

        return jsonify({
            "ok": False,
            "msg": "نام فایل مشخص نشده"
        }), 400

    # جلوگیری از دسترسی به مسیرهای خارج از downloads
    filename = os.path.basename(
        filename
    )

    filepath = os.path.join(
        OUTPUT_DIR,
        filename
    )

    if not os.path.isfile(filepath):

        return jsonify({
            "ok": False,
            "msg": "فایل پیدا نشد"
        }), 404

    return send_file(
        filepath,
        as_attachment=True,
        download_name=filename
    )


if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "10000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
