FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV TORCH_HOME=/app/.cache/torch
ENV HF_HOME=/app/.cache/huggingface

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-venv python3-pip \
    ffmpeg libsm6 libxext6 libglib2.0-0 libgl1 git curl \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/bin/python

# Python deps
RUN pip install --no-cache-dir --break-system-packages setuptools wheel

COPY pyproject.toml .
RUN pip install --no-cache-dir --break-system-packages -e ".[dev]"

# Install torch with CUDA support (override the CPU version from deps)
RUN pip install --no-cache-dir --break-system-packages \
    torch torchvision --index-url https://download.pytorch.org/whl/cu124

# Download YOLOv8x model (130MB)
RUN python -c "from ultralytics import YOLO; YOLO('yolov8x.pt')"

# Pre-download MiewID ReID model (~200MB)
RUN python -c "from huggingface_hub import hf_hub_download; hf_hub_download('conservationxlabs/miewid-msv3', 'model.safetensors')"

# Pre-download OSNet fallback (~10MB)
RUN python -c "from boxmot.reid.core import ReID; ReID(device='cpu')"

# Cache timm model config for MiewID preprocessing
RUN python -c "import timm; timm.create_model('efficientnetv2_rw_m', pretrained=False, num_classes=0)"

COPY . .

# Model paths for the app
ENV YOLO_MODEL=/app/yolov8x.pt

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
