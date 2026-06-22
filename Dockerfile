FROM node:20-alpine AS frontend-build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM nginx:1.27-alpine AS frontend
COPY --from=frontend-build /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
RUN chown -R nginx:nginx /usr/share/nginx/html /etc/nginx/conf.d
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

FROM python:3.11-slim AS backend
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsm6 libxext6 libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --default-timeout=1000 --retries=10 --upgrade pip setuptools wheel
COPY backend/pyproject.toml .
RUN useradd --system --no-create-home appuser
COPY --chown=appuser:appuser backend/ .
RUN pip install --no-cache-dir --default-timeout=1000 --retries=10 -e "."
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM nvcr.io/nvidia/l4t-pytorch:r36.3.0-pth2.2-py3 AS backend-jetson
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsm6 libxext6 libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --default-timeout=1000 --retries=10 --upgrade pip setuptools wheel
COPY backend/pyproject.toml .
RUN useradd --system --no-create-home appuser
COPY --chown=appuser:appuser backend/ .
RUN pip install --no-cache-dir --default-timeout=1000 --retries=10 -e "."
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
