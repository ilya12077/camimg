import os
from functools import lru_cache
import requests
from dotenv import find_dotenv, load_dotenv
from flask import Flask, request
from flask import Response
from waitress import serve
from concurrent.futures import ThreadPoolExecutor
import subprocess
import tempfile

load_dotenv(find_dotenv())
app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=50)

AUTH_TOKEN = os.environ.get('AUTH_TOKEN')
PASSWORD = os.environ.get('PASSWORD')
EXTERNAL_SERVER = os.environ.get('EXTERNAL_SERVER')

session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {AUTH_TOKEN}",
    "User-Agent": "CamImgProxy/1.0"
})


@lru_cache(maxsize=300)  # Кэш на 100 изображений
def fetch_image_cached(image_name):
    """Получение изображения с кэшированием"""
    external_url = f"{EXTERNAL_SERVER}/{image_name}"

    response = session.get(
        external_url,
        timeout=5,
        verify=True
    )
    response.raise_for_status()

    return response.content


@app.route('/camimg')
def proxy_image():
    passw = request.args.get('pass')
    image_name = request.args.get('img')

    if not passw or not image_name:
        return "Missing parameters", 400

    if passw != PASSWORD:
        return "Unauthorized", 401

    try:
        # Проверяем расширение файла
        if not image_name.lower().endswith(('.jpg', '.jpeg')):
            return "Invalid image format", 400

        # Получаем изображение (из кэша или загружаем)
        content = fetch_image_cached(image_name)
        # ===== ОТДАЁМ КАК ГОТОВЫЙ ФАЙЛ =====
        return Response(
            content,
            content_type="image/jpeg",
            headers={
                'Content-Disposition': f'inline; filename="{image_name.split("/")[-1]}"',
                'Content-Length': str(len(content)),
                'Accept-Ranges': 'bytes'  # Поддержка докачки
            },
            status=200
        )
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return "Image not found", 404
        return f"HTTP Error: {str(e)}", e.response.status_code
    except Exception as e:
        return f"Internal error: {str(e)}", 500


def make_mp4(image_names):
    futures = [executor.submit(fetch_image_cached, name) for name in image_names]

    FFMPEG = "ffmpeg" if os.environ.get('AM_I_IN_A_DOCKER_CONTAINER', False) else r"C:\Program Files (x86)\ffmpeg\ffmpeg.exe"

    # Создаём временный файл
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp_file:
        tmp_path = tmp_file.name

    try:
        process = subprocess.Popen(
            [
                FFMPEG,
                "-hide_banner",
                "-loglevel", "error",

                "-f", "image2pipe",
                "-vcodec", "mjpeg",
                "-i", "-",

                "-vf", "setpts=5.0*PTS,scale=800:600:force_original_aspect_ratio=decrease",  # <-- Замедление через фильтры

                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "32",
                "-tune", "fastdecode",
                "-pix_fmt", "yuv420p",

                "-movflags", "+faststart",


                "-y",
                tmp_path,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        for future in futures:
            try:
                process.stdin.write(future.result())
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    continue
                raise
        process.stdin.close()
        process.wait()

        if process.returncode != 0:
            error = process.stderr.read()
            raise RuntimeError(error.decode(errors="ignore"))

        # Читаем файл
        with open(tmp_path, 'rb') as f:
            video_data = f.read()
    finally:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    return video_data


@app.route('/camgif')
def proxy_video():
    passw = request.args.get('pass')
    image_name = request.args.get('img')

    if not passw or not image_name:
        return "Missing parameters", 400

    if passw != PASSWORD:
        return "Unauthorized", 401

    try:
        if not image_name.lower().endswith(('.jpg', '.jpeg', '.png')):
            return "Invalid image format", 400

        # Разделяем путь и имя файла
        folder, filename = image_name.rsplit('/', 1)

        # Отрезаем "_5.jpg"
        prefix = filename.rsplit('_', 1)[0]

        # Формируем список кадров _0 ... _10
        image_names = [
            f"{folder}/{prefix}_{i}.jpg"
            for i in range(30)
        ]
        # ===== ГЕНЕРИРУЕМ ВИДЕО В ПАМЯТИ =====
        video_data = make_mp4(image_names)

        # ===== ОТДАЁМ КАК ГОТОВЫЙ ФАЙЛ =====
        return Response(
            video_data,
            content_type="video/mp4",
            headers={
                'Content-Disposition': 'inline; filename="video.mp4"',
                'Content-Length': str(len(video_data))
            }
        )

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return "Image not found", 404
        return f"HTTP Error: {str(e)}", e.response.status_code
    except Exception as e:
        return f"Internal error: {str(e)}", 500


if __name__ == '__main__':
    if os.environ.get('AM_I_IN_A_DOCKER_CONTAINER', False):
        serve(app, host='0.0.0.0', port=8867, url_scheme='http')
    else:
        app.run(host='0.0.0.0', port=8867)
