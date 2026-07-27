FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-venv python3-pip \
    ffmpeg \
    libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

WORKDIR /app

COPY cv_engine/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY cv_engine/ .

RUN mkdir -p stream_cache

EXPOSE 8700

CMD ["python", "-m", "uvicorn", "cv_engine.server:app", "--host", "0.0.0.0", "--port", "8700"]
