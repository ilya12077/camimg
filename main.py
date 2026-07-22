import os
from functools import lru_cache
import requests
from dotenv import find_dotenv, load_dotenv
from flask import Flask, request
from flask import Response
from waitress import serve

load_dotenv(find_dotenv())
app = Flask(__name__)

AUTH_TOKEN = os.environ.get('AUTH_TOKEN')
PASSWORD = os.environ.get('PASSWORD')
EXTERNAL_SERVER = os.environ.get('EXTERNAL_SERVER')


@lru_cache(maxsize=20)  # Кэш на 100 изображений
def fetch_image_cached(image_name):
    """Получение изображения с кэшированием"""
    external_url = f"{EXTERNAL_SERVER}/{image_name}"

    headers = {
        'Authorization': f"Bearer {AUTH_TOKEN}",
        'User-Agent': 'Python-Proxy-Server'
    }

    response = requests.get(
        external_url,
        headers=headers,
        timeout=3,
        verify=True
    )
    response.raise_for_status()

    return response.content, response.headers.get('content-type', 'image/jpeg')


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
        content, content_type = fetch_image_cached(image_name)

        return Response(
            content,
            content_type=content_type,
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


if __name__ == '__main__':
    if os.environ.get('AM_I_IN_A_DOCKER_CONTAINER', False):
        serve(app, host='0.0.0.0', port=8867, url_scheme='http')
    else:
        app.run(host='192.168.1.10', port=8867)
