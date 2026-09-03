import threading
import queue
import os
from flask import Flask, render_template, request, jsonify, send_file
from yt_dlp import YoutubeDL

app = Flask(__name__)

# ============================================================
# QUEUE
# ============================================================

job_queue = queue.Queue()

progress = {
    "state": "idle",
    "current_index": 0,
    "total": 0,
    "current_title": "",
    "percent": "",
    "speed": "",
    "eta": "",
    "filename": "",
    "log": []
}

# ============================================================
# DOWNLOAD DIRECTORY
# ============================================================

OUTPUT_DIR = os.path.abspath("downloads")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ============================================================
# LOG
# ============================================================

def append_log(msg):
    progress["log"].append(msg)

    if len(progress["log"]) > 500:
        progress["log"] = progress["log"][-500:]


# ============================================================
# PROGRESS HOOK
# ============================================================

def progress_hook(d):

    if d.get("status") == "downloading":

        progress["state"] = "downloading"

        progress["percent"] = (
            d.get("_percent_str") or ""
        ).strip()

        progress["eta"] = (
            d.get("_eta_str") or ""
        )

        progress["speed"] = (
            d.get("_speed_str") or ""
        )

        progress["filename"] = (
            d.get("filename") or ""
        )

    elif d.get("status") == "finished":

        progress["percent"] = "100%"
        progress["eta"] = "0"
        progress["speed"] = ""

        append_log(
            "✅ Finished: " +
            (progress.get("current_title") or "")
        )


# ============================================================
# COMMON YT-DLP OPTIONS
# ============================================================

def common_ydl_opts():

    return {

        # فعال کردن استخراج های لازم YouTube
        "quiet": True,
        "no_warnings": False,

        # تعداد تلاش
        "retries": 10,
        "fragment_retries": 10,

        # جلوگیری از فایل part
        "nopart": True,

        # از ادامه دانلود قبلی استفاده نکند
        "continuedl": False,

        # محدود کردن نام فایل
        "restrictfilenames": True,

        # User Agent
        "http_headers": {
            "User-Agent":
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/151.0.0.0 Safari/537.36"
        },

        # استخراج اطلاعات کامل
        "extract_flat": False,
    }


# ============================================================
# DOWNLOAD OPTIONS
# ============================================================

def build_ydl_opts(quality, ffmpeg_location):

    ydl_opts = common_ydl_opts()

    # --------------------------------------------------------
    # FORMAT
    # --------------------------------------------------------

    if quality == "240":

        fmt = (
            "bestvideo[height<=240]+bestaudio/"
            "best[height<=240]"
        )

    elif quality == "360":

        fmt = (
            "bestvideo[height<=360]+bestaudio/"
            "best[height<=360]/"
            "best"
        )

    elif quality == "480":

        fmt = (
            "bestvideo[height<=480]+bestaudio/"
            "best[height<=480]/"
            "best"
        )

    elif quality == "720":

        fmt = (
            "bestvideo[height<=720]+bestaudio/"
            "best[height<=720]/"
            "best"
        )

    elif quality == "1080":

        fmt = (
            "bestvideo[height<=1080]+bestaudio/"
            "best[height<=1080]/"
            "best"
        )

    else:

        fmt = (
            "bestvideo+bestaudio/"
            "best"
        )

    ydl_opts["format"] = fmt

    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

    ydl_opts["merge_output_format"] = "mp4"

    ydl_opts["outtmpl"] = os.path.join(
        OUTPUT_DIR,
        "%(title)s.%(ext)s"
    )

    # --------------------------------------------------------
    # PROGRESS
    # --------------------------------------------------------

    ydl_opts["progress_hooks"] = [
        progress_hook
    ]

    ydl_opts["noprogress"] = True

    # --------------------------------------------------------
    # FFMPEG
    # --------------------------------------------------------

    if ffmpeg_location:

        ydl_opts["ffmpeg_location"] = (
            ffmpeg_location
        )

    return ydl_opts


# ============================================================
# ANALYZE LINKS
# ============================================================

def analyze_links(raw_links):

    links = [
        ln.strip()
        for ln in raw_links.splitlines()
        if ln.strip()
    ]

    results = []

    ydl_opts = common_ydl_opts()

    # برای تحلیل نیازی به دانلود نیست
    ydl_opts["skip_download"] = True

    with YoutubeDL(ydl_opts) as ydl:

        for ln in links:

            try:

                append_log(
                    f"🔎 بررسی لینک: {ln}"
                )

                # ------------------------------------------------
                # استخراج اطلاعات
                # ------------------------------------------------

                info = ydl.extract_info(
                    ln,
                    download=False
                )

                if not info:

                    raise Exception(
                        "اطلاعات ویدئو دریافت نشد"
                    )

                # ------------------------------------------------
                # TITLE
                # ------------------------------------------------

                title = info.get(
                    "title",
                    "بدون عنوان"
                )

                # ------------------------------------------------
                # THUMBNAIL
                # ------------------------------------------------

                thumbnail = info.get(
                    "thumbnail",
                    ""
                )

                # ------------------------------------------------
                # PAGE URL
                # ------------------------------------------------

                webpage_url = info.get(
                    "webpage_url",
                    ln
                )

                # ------------------------------------------------
                # DIRECT URL
                # ------------------------------------------------

                direct_url = info.get(
                    "url",
                    ""
                )

                # ------------------------------------------------
                # ID
                # ------------------------------------------------

                video_id = info.get(
                    "id",
                    ""
                )

                # ------------------------------------------------
                # DURATION
                # ------------------------------------------------

                duration = info.get(
                    "duration",
                    0
                )

                # ------------------------------------------------
                # EXTRACTED FORMAT
                # ------------------------------------------------

                ext = info.get(
                    "ext",
                    ""
                )

                # ------------------------------------------------
                # HEIGHT
                # ------------------------------------------------

                height = info.get(
                    "height",
                    0
                )

                # ------------------------------------------------
                # RESULT
                # ------------------------------------------------

                results.append({

                    "title": title,

                    "thumbnail": thumbnail,

                    "url": webpage_url,

                    "direct_url": direct_url,

                    "id": video_id,

                    "duration": duration,

                    "ext": ext,

                    "height": height,

                    "error": ""

                })

                append_log(
                    f"✅ لینک با موفقیت خوانده شد: "
                    f"{title}"
                )

            except Exception as e:

                # ------------------------------------------------
                # خطای واقعی را استخراج کن
                # ------------------------------------------------

                error_text = str(e)

                append_log(
                    f"❌ خطا در بررسی {ln}: "
                    f"{error_text}"
                )

                results.append({

                    "title":
                        f"خطا در خواندن: {ln}",

                    "thumbnail": "",

                    "url": ln,

                    "direct_url": "",

                    "id": "",

                    "duration": 0,

                    "ext": "",

                    "height": 0,

                    "error": error_text

                )

    return results


# ============================================================
# DOWNLOAD WORKER
# ============================================================

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

                "state":
                    "downloading",

                "current_index":
                    0,

                "total":
                    len(links),

                "current_title":
                    "",

                "percent":
                    "",

                "speed":
                    "",

                "eta":
                    "",

                "filename":
                    ""

            })

            append_log(
                f"▶ شروع دانلود {len(links)} مورد - "
                f"کیفیت: {quality}"
            )

            # ----------------------------------------------------
            # YT-DLP OPTIONS
            # ----------------------------------------------------

            ydl_opts = build_ydl_opts(
                quality,
                ffmpeg_location
            )

            # ----------------------------------------------------
            # DOWNLOAD
            # ----------------------------------------------------

            with YoutubeDL(ydl_opts) as ydl:

                for i, ln in enumerate(
                    links,
                    1
                ):

                    progress[
                        "current_index"
                    ] = i

                    # ------------------------------------------------
                    # READ TITLE
                    # ------------------------------------------------

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

                    except Exception as e:

                        progress[
                            "current_title"
                        ] = ln

                        append_log(
                            f"⚠️ نتوانست عنوان را بخواند: "
                            f"{e}"
                        )

                    append_log(
                        f"⬇ {i}/{len(links)}: "
                        f"{progress['current_title']}"
                    )

                    # ------------------------------------------------
                    # DOWNLOAD
                    # ------------------------------------------------

                    try:

                        ydl.download(
                            [ln]
                        )

                        append_log(
                            f"✅ دانلود شد: "
                            f"{progress['current_title']}"
                        )

                    except Exception as e:

                        append_log(
                            f"❌ خطا در دانلود: "
                            f"{ln} -> {e}"
                        )

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


# ============================================================
# START WORKER
# ============================================================

t = threading.Thread(
    target=download_worker,
    daemon=True
)

t.start()


# ============================================================
# HOME
# ============================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


# ============================================================
# ANALYZE
# ============================================================

@app.route(
    "/analyze",
    methods=["POST"]
)
def analyze():

    try:

        data = request.get_json(
            force=True
        )

        raw_links = data.get(
            "links",
            ""
        )

        if not raw_links.strip():

            return jsonify({
                "items": []
            })

        progress[
            "state"
        ] = "analyzing"

        progress[
            "log"
        ] = []

        items = analyze_links(
            raw_links
        )

        progress[
            "state"
        ] = "idle"

        return jsonify({

            "items": items,

            "ok": True

        })

    except Exception as e:

        progress[
            "state"
        ] = "error"

        append_log(
            f"❌ خطا در Analyze: {e}"
        )

        return jsonify({

            "items": [],

            "ok": False,

            "error": str(e)

        }), 500


# ============================================================
# START DOWNLOAD
# ============================================================

@app.route(
    "/start",
    methods=["POST"]
)
def start():

    try:

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

                "msg":
                    "هیچ لینکی وارد نشده"

            }), 400

        # --------------------------------------------------------
        # RESET PROGRESS
        # --------------------------------------------------------

        progress.update({

            "state":
                "queued",

            "current_index":
                0,

            "total":
                len(links),

            "current_title":
                "",

            "percent":
                "",

            "speed":
                "",

            "eta":
                "",

            "filename":
                "",

            "log":
                []

        })

        # --------------------------------------------------------
        # ADD JOB
        # --------------------------------------------------------

        job_queue.put({

            "links":
                links,

            "quality":
                quality,

            "ffmpeg":
                ffmpeg_loc

        })

        return jsonify({

            "ok":
                True,

            "msg":
                "در صف دانلود قرار گرفت"

        })

    except Exception as e:

        return jsonify({

            "ok":
                False,

            "msg":
                str(e)

        }), 500


# ============================================================
# PROGRESS
# ============================================================

@app.route("/progress")
def get_progress():

    return jsonify(
        progress
    )


# ============================================================
# DOWNLOAD FILE TO USER
# ============================================================

@app.route("/download")
def download_file():

    filename = request.args.get(
        "filename",
        ""
    ).strip()

    if not filename:

        return jsonify({

            "ok":
                False,

            "msg":
                "نام فایل مشخص نشده"

        }), 400

    # جلوگیری از دسترسی به مسیرهای خارج از downloads

    filename = os.path.basename(
        filename
    )

    filepath = os.path.join(
        OUTPUT_DIR,
        filename
    )

    if not os.path.isfile(
        filepath
    ):

        return jsonify({

            "ok":
                False,

            "msg":
                "فایل پیدا نشد"

        }), 404

    return send_file(

        filepath,

        as_attachment=True,

        download_name=filename

    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    return jsonify({

        "status":
            "ok"

    })


# ============================================================
# RUN
# ============================================================

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
