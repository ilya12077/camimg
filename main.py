import os
from functools import lru_cache
import requests
from dotenv import find_dotenv, load_dotenv
from flask import Flask, request
from flask import Response
from waitress import serve
from PIL import Image
import io
from concurrent.futures import ThreadPoolExecutor, as_completed

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


def make_gif(image_names, duration=150):
    futures = [executor.submit(fetch_image_cached, name) for name in image_names]

    frames = []

    for future in futures:
        try:
            image = future.result()

            image = compress_and_resize_bytes(
                image,
                max_width=320,
                max_height=240,
                quality=65
            )

            frames.append(Image.open(io.BytesIO(image)))

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                continue
            raise

    if not frames:
        raise FileNotFoundError("No frames found")

    output = io.BytesIO()

    frames[0].save(
        output,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=0,
        optimize=False,
    )

    output.seek(0)
    return output.getvalue()


def compress_and_resize_bytes(image_bytes, max_width=800, max_height=600, quality=65):
    # Загружаем изображение
    img = Image.open(io.BytesIO(image_bytes))

    # Конвертируем в RGB
    if img.mode in ('RGBA', 'LA', 'P'):
        img = img.convert('RGB')

    # Уменьшаем разрешение, если заданы параметры
    if max_width or max_height:
        original_width, original_height = img.size

        # Вычисляем новые размеры с сохранением пропорций
        new_width = original_width
        new_height = original_height

        if max_width and original_width > max_width:
            ratio = max_width / original_width
            new_width = max_width
            new_height = int(original_height * ratio)

        if max_height and new_height > max_height:
            ratio = max_height / new_height
            new_height = max_height
            new_width = int(new_width * ratio)

        # Применяем изменение размера (resample - алгоритм пересчёта пикселей)
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # Сохраняем со сжатием
    output_buffer = io.BytesIO()
    img.save(output_buffer, format='JPEG', quality=quality, optimize=True)

    return output_buffer.getvalue()


@lru_cache(maxsize=256)  # Кэш на 100 изображений
def fetch_image_cached(image_name):
    """Получение изображения с кэшированием"""
    external_url = f"{EXTERNAL_SERVER}/{image_name}"

    response = session.get(
        external_url,
        timeout=(3, 5),
        verify=True
    )
    response.raise_for_status()
    # compressed = compress_and_resize_bytes(response.content, max_width=800, max_height=600, quality=65)

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
        if not image_name.lower().endswith(('.jpg', '.jpeg', '.png')):
            return "Invalid image format", 400

        # Получаем изображение (из кэша или загружаем)
        content = fetch_image_cached(image_name)
        content = compress_and_resize_bytes(content, max_width=800, max_height=600, quality=65)
        return Response(
            content,
            content_type="image/jpeg",
            status=200
        )

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return "Image not found", 404
        return f"HTTP Error: {str(e)}", e.response.status_code
    except Exception as e:
        return f"Internal error: {str(e)}", 500


@app.route('/camimg/clear_cache')
def clear_cache():
    """Очистка кэша (опционально)"""
    fetch_image_cached.cache_clear()
    return "Cache cleared", 200


@app.route('/camgif')
def proxy_gif():
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

        gif = make_gif(image_names)

        return Response(
            gif,
            content_type='image/gif',
            status=200
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
