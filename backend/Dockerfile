FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive \
    DEEPFACE_HOME=/app/.deepface

WORKDIR /app

# Dependências de sistema:
# - build-essential, cmake, libboost-all-dev: necessários caso o dlib precise compilar.
# - libgl1, libglib2.0-0, libsm6, libxext6, libxrender1, libgomp1: necessários para
#   OpenCV e MediaPipe rodarem em headless.
# - ffmpeg: utilitário usado por backends de imagem/vídeo.
# Caso o dlib falhe na compilação, o sistema continua funcional via OpenCV (fallback
# já tratado em face_service.py).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        libboost-all-dev \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        libgomp1 \
        ffmpeg \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip setuptools wheel \
    && pip install -r /app/requirements.txt

COPY . /app

RUN mkdir -p /app/data /app/auditoria /app/rostos_cadastrados /app/.deepface

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
