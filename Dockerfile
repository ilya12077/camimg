FROM python:3.11-slim

# ========== НАСТРОЙКА ОКРУЖЕНИЯ ==========
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    AM_I_IN_A_DOCKER_CONTAINER=Yes

# ========== СЛОЙ 1: Системные пакеты (кэшируется) ==========
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        emacs \
        ffmpeg \
    && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# ========== СЛОЙ 2: Клонирование репозитория ==========
# Клонируем в отдельную папку для кэширования
RUN git clone https://github.com/ilya12077/camimg.git /tmp/camimg

# ========== СЛОЙ 3: Установка Python зависимостей (кэшируется) ==========
# Копируем только requirements.txt из клонированного репозитория
RUN pip install --no-cache-dir -r /tmp/camimg/requirements.txt

# ========== СЛОЙ 4: Копирование кода приложения ==========
RUN mkdir -p /etc/camimg && \
    cp -a /tmp/camimg/. /etc/camimg/ && \
    rm -rf /tmp/camimg

# ========== ЗАПУСК ==========
EXPOSE 8867/tcp

WORKDIR /etc/camimg

CMD ["python", "/etc/camimg/main.py"]