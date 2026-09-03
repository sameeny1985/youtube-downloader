import os
import queue
import threading

from flask import Flask, render_template, request, jsonify, send_file
from yt_dlp import YoutubeDL


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)


# ============================================================
# DOWNLOAD QUEUE
# ============================================================

job_queue = queue.Queue()


# ============================================================
# PROGRESS
# ============================================================

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

os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)


# ============================================================
# LOG FUNCTION
# ============================================================

def append_log(message):

    progress["log"].append(
        str(message)
    )

    if len(progress["log"]) > 500:

        progress["log"] = (
            progress["log"][-500:]
        )


# ============================================================
# PROGRESS HOOK
# ============================================================

def progress_hook(data):

    status = data.get(
        "status"
    )

    if status == "downloading":

        progress["state"] = "downloading"

        progress["percent"] = (
            data.get("_percent_str")
            or ""
        ).strip()

        progress["speed"] = (
            data.get("_speed_str")
            or ""
        )

        progress["eta"] = (
            data.get("_eta_str")
            or ""
        )

        progress["filename"] = (
            data.get("filename")
            or ""
        )

    elif status == "finished":

        progress["percent"] = "100%"

        progress["eta"] = "0"

        progress["speed"] = ""

        append_log(
            "✅ دانلود ویدئو تمام شد."
        )


# ============================================================
# COMMON YT-DLP OPTIONS
# ============================================================

def get_common_ydl_opts():

    return {

        "quiet": True,

        "no_warnings": False,

        "noprogress": True,

        "retries": 20,

        "fragment_retries": 20,

        "retry_sleep": 2,

        "continuedl": False,

        "nopart": True,

        "restrictfilenames": True,

        "extract_flat": False,

        "http_headers": {

            "User-Agent":
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/151.0.0.0 "
                "Safari/537.36"

        }

    }


# ============================================================
# BUILD DOWNLOAD OPTIONS
# ============================================================

def build_ydl_opts(
    quality="360",
    ffmpeg_location=""
):

    ydl_opts = get_common_ydl_opts()


    # --------------------------------------------------------
    # QUALITY
    # --------------------------------------------------------

    if quality == "240":

        fmt = (
            "bestvideo[height<=240]+bestaudio/"
            "best[height<=240]/"
            "best"
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


    # --------------------------------------------------------
    # FORMAT
    # --------------------------------------------------------

    ydl_opts["format"] = fmt

    ydl_opts["merge_output_format"] = "mp4"


    # --------------------------------------------------------
    # OUTPUT FILE
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # FFMPEG
    # --------------------------------------------------------

    if ffmpeg_location:

        ydl_opts["ffmpeg_location"] = (
            ffmpeg_location
        )


    return ydl_opts


# ============================================================
# ANALYZE YOUTUBE LINKS
# ============================================================

def analyze_links(raw_links):

    links = [

        line.strip()

        for line in raw_links.splitlines()

        if line.strip()

    ]

    results = []


    # --------------------------------------------------------
    # OPTIONS FOR ANALYSIS
    # --------------------------------------------------------

    ydl_opts = get_common_ydl_opts()

    ydl_opts["skip_download"] = True


    # --------------------------------------------------------
    # YT-DLP
    # --------------------------------------------------------

    with YoutubeDL(ydl_opts) as ydl:

        for link in links:

            try:

                append_log(
                    f"🔎 بررسی لینک: {link}"
                )


                # ------------------------------------------------
                # EXTRACT INFO
                # ------------------------------------------------

                info = ydl.extract_info(
                    link,
                    download=False
                )


                if not info:

                    raise Exception(
                        "اطلاعات ویدئو دریافت نشد."
                    )


                # ------------------------------------------------
                # DATA
                # ------------------------------------------------

                title = info.get(
                    "title",
                    "بدون عنوان"
                )

                thumbnail = info.get(
                    "thumbnail",
                    ""
                )

                webpage_url = info.get(
                    "webpage_url",
                    link
                )

                video_id = info.get(
                    "id",
                    ""
                )

                duration = info.get(
                    "duration",
                    0
                )

                ext = info.get(
                    "ext",
                    ""
                )

                height = info.get(
                    "height",
                    0
                )

                # ------------------------------------------------
                # DIRECT URL
                # ------------------------------------------------

                direct_url = info.get(
                    "url",
                    ""
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
                    f"✅ لینک خوانده شد: {title}"
                )


            except Exception as error:

                error_text = str(
                    error
                )


                append_log(
                    f"❌ خطا در خواندن لینک: "
                    f"{link}"
                )

                append_log(
                    f"❌ جزئیات خطا: "
                    f"{error_text}"
                )


                results.append({

                    "title":
                        f"خطا در خواندن: {link}",

                    "thumbnail": "",

                    "url": link,

                    "direct_url": "",

                    "id": "",

                    "duration": 0,

                    "ext": "",

                    "height": 0,

                    "error": error_text

                })


    return results


# ============================================================
# DOWNLOAD WORKER
# ============================================================

def download_worker():

    while True:

        task = job_queue.get()


        if task is None:

            job_queue.task_done()

            break


        try:

            links = task.get(
                "links",
                []
            )

            quality = task.get(
                "quality",
                "360"
            )

            ffmpeg_location = task.get(
                "ffmpeg",
                ""
            )


            # ------------------------------------------------
            # RESET
            # ------------------------------------------------

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
                f"▶ شروع دانلود "
                f"{len(links)} ویدئو "
                f"با کیفیت {quality}p"
            )


            # ------------------------------------------------
            # OPTIONS
            # ------------------------------------------------

            ydl_opts = build_ydl_opts(
                quality,
                ffmpeg_location
            )


            # ------------------------------------------------
            # DOWNLOAD
            # ------------------------------------------------

            with YoutubeDL(
                ydl_opts
            ) as ydl:

                for index, link in enumerate(
                    links,
                    start=1
                ):

                    progress[
                        "current_index"
                    ] = index


                    # --------------------------------------------
                    # GET TITLE
                    # --------------------------------------------

                    try:

                        info = ydl.extract_info(
                            link,
                            download=False
                        )

                        title = info.get(
                            "title",
                            link
                        )

                        progress[
                            "current_title"
                        ] = title


                    except Exception as error:

                        title = link

                        progress[
                            "current_title"
                        ] = link

                        append_log(
                            f"⚠️ خطا در خواندن عنوان: "
                            f"{error}"
                        )


                    append_log(
                        f"⬇️ {index}/{len(links)} "
                        f"{title}"
                    )


                    # --------------------------------------------
                    # DOWNLOAD
                    # --------------------------------------------

                    try:

                        ydl.download(
                            [link]
                        )

                        append_log(
                            f"✅ دانلود شد: {title}"
                        )


                    except Exception as error:

                        append_log(
                            f"❌ خطا در دانلود: "
                            f"{link}"
                        )

                        append_log(
                            f"❌ جزئیات: "
                            f"{error}"
                        )


            # ------------------------------------------------
            # FINISHED
            # ------------------------------------------------

            progress[
                "state"
            ] = "done"

            append_log(
                "✅ تمام دانلودها به پایان رسید."
            )


        except Exception as error:

            progress[
                "state"
            ] = "error"

            append_log(
                f"❌ خطای عمومی: {error}"
            )


        finally:

            job_queue.task_done()


# ============================================================
# START WORKER THREAD
# ============================================================

worker_thread = threading.Thread(

    target=download_worker,

    daemon=True

)

worker_thread.start()


# ============================================================
# HOME
# ============================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


# ============================================================
# ANALYZE API
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

                "ok": False,

                "items": [],

                "error":
                    "هیچ لینکی وارد نشده است."

            }), 400


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

            "ok": True,

            "items": items

        })


    except Exception as error:

        progress[
            "state"
        ] = "error"


        append_log(
            f"❌ خطای Analyze: {error}"
        )


        return jsonify({

            "ok": False,

            "items": [],

            "error": str(error)

        }), 500


# ============================================================
# START DOWNLOAD API
# ============================================================

@app.route(
    "/start",
    methods=["POST"]
)
def start_download():

    try:

        data = request.get_json(
            force=True
        )


        raw_links = data.get(
            "links",
            ""
        )


        links = [

            line.strip()

            for line in raw_links.splitlines()

            if line.strip()

        ]


        quality = str(
            data.get(
                "quality",
                "360"
            )
        )


        ffmpeg_location = data.get(
            "ffmpeg",
            ""
        )


        if not links:

            return jsonify({

                "ok": False,

                "msg":
                    "هیچ لینکی وارد نشده است."

            }), 400


        # ------------------------------------------------
        # RESET PROGRESS
        # ------------------------------------------------

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


        # ------------------------------------------------
        # ADD JOB
        # ------------------------------------------------

        job_queue.put({

            "links":
                links,

            "quality":
                quality,

            "ffmpeg":
                ffmpeg_location

        })


        return jsonify({

            "ok":
                True,

            "msg":
                "دانلود در صف قرار گرفت."

        })


    except Exception as error:

        return jsonify({

            "ok":
                False,

            "msg":
                str(error)

        }), 500


# ============================================================
# PROGRESS API
# ============================================================

@app.route(
    "/progress"
)
def get_progress():

    return jsonify(
        progress
    )


# ============================================================
# DOWNLOAD FILE API
# ============================================================

@app.route(
    "/download"
)
def download_file():

    filename = request.args.get(
        "filename",
        ""
    ).strip()


    if not filename:

        return jsonify({

            "ok": False,

            "msg":
                "نام فایل مشخص نشده است."

        }), 400


    # ------------------------------------------------
    # SECURITY
    # ------------------------------------------------

    filename = os.path.basename(
        filename
    )


    filepath = os.path.join(
        OUTPUT_DIR,
        filename
    )


    # ------------------------------------------------
    # CHECK FILE
    # ------------------------------------------------

    if not os.path.isfile(
        filepath
    ):

        return jsonify({

            "ok": False,

            "msg":
                "فایل پیدا نشد."

        }), 404


    # ------------------------------------------------
    # SEND FILE
    # ------------------------------------------------

    return send_file(

        filepath,

        as_attachment=True,

        download_name=filename

    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route(
    "/health"
)
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
