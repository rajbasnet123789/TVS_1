import os


class Settings:
    BUSINESS_BACKEND_URL: str = os.getenv("BUSINESS_BACKEND_URL", "http://backend:8000")
    INFLUX_URL: str = os.getenv("INFLUX_URL", "http://influxdb:8086")
    INFLUX_TOKEN: str = os.getenv("INFLUX_TOKEN", "")
    INFLUX_ORG: str = os.getenv("INFLUX_ORG", "poultry")
    INFLUX_BUCKET: str = os.getenv("INFLUX_BUCKET", "detections")
    MQTT_BROKER: str = os.getenv("MQTT_BROKER", "mosquitto")
    MQTT_PORT: int = int(os.getenv("MQTT_PORT", "1883"))
    JWT_SECRET: str = os.getenv("JWT_SECRET", "").strip()
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    # Shared secret for authenticating cv-engine → backend internal API calls
    CV_ENGINE_API_KEY: str = os.getenv("CV_ENGINE_API_KEY", "")
    GO2RTC_API_URL: str = os.getenv("GO2RTC_API_URL", "http://localhost:1984")
    GO2RTC_RTSP_URL: str = os.getenv("GO2RTC_RTSP_URL", "rtsp://localhost:8554")
    STREAM_CACHE_DIR: str = os.getenv("STREAM_CACHE_DIR", "stream_cache")
    DETECTION_CONFIDENCE: float = float(os.getenv("DETECTION_CONFIDENCE", "0.55"))
    MODEL_PATH: str = os.getenv("MODEL_PATH", "AI_MODEL/best.pt")
    # Inference speed tuning: run YOLO at this resolution (smaller = faster) and
    # at most this often (skip frames between runs). Live video is unaffected —
    # it streams via a separate MJPEG path.
    INFERENCE_IMGSZ: int = int(os.getenv("INFERENCE_IMGSZ", "640"))
    INFERENCE_MIN_INTERVAL_MS: int = int(os.getenv("INFERENCE_MIN_INTERVAL_MS", "400"))
    # How often cv-engine pushes live per-camera counts to the backend (seconds).
    COUNTS_PUSH_INTERVAL_SECONDS: float = float(os.getenv("COUNTS_PUSH_INTERVAL_SECONDS", "1"))
    # Live count is the number of UNIQUE track IDs seen in the last N seconds
    # (per camera). This smooths out per-frame YOLO jitter (occlusion, missed
    # frames, confidence flicker) instead of reporting a raw box count.
    LIVE_COUNT_WINDOW_SECONDS: int = int(os.getenv("LIVE_COUNT_WINDOW_SECONDS", "20"))
    # If a camera stops producing count events for this long, report its count
    # as 0 so offline/stalled cameras don't show stale numbers forever.
    LIVE_COUNT_TTL_SECONDS: int = int(os.getenv("LIVE_COUNT_TTL_SECONDS", "30"))
    # Output frame rate of the ffmpeg MJPEG capture loop. Frames are consumed
    # by the inference loop (throttled by INFERENCE_MIN_INTERVAL_MS), so a low
    # rate avoids wasted decode + copy work. No other consumer reads frames.
    CAPTURE_FPS: int = int(os.getenv("CAPTURE_FPS", "5"))


settings = Settings()

