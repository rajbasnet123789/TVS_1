import os


class Settings:
    BUSINESS_BACKEND_URL: str = os.getenv("BUSINESS_BACKEND_URL", "http://backend:8000")
    INFLUX_URL: str = os.getenv("INFLUX_URL", "http://influxdb:8086")
    INFLUX_TOKEN: str = os.getenv("INFLUX_TOKEN", "")
    INFLUX_ORG: str = os.getenv("INFLUX_ORG", "poultry")
    INFLUX_BUCKET: str = os.getenv("INFLUX_BUCKET", "detections")
    MQTT_BROKER: str = os.getenv("MQTT_BROKER", "mosquitto")
    MQTT_PORT: int = int(os.getenv("MQTT_PORT", "1883"))
    JWT_SECRET: str = os.getenv("JWT_SECRET", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    # Shared secret for authenticating cv-engine → backend internal API calls
    CV_ENGINE_API_KEY: str = os.getenv("CV_ENGINE_API_KEY", "")
    STREAM_CACHE_DIR: str = os.getenv("STREAM_CACHE_DIR", "stream_cache")
    WS_POLL_INTERVAL_MS: int = int(os.getenv("WS_POLL_INTERVAL_MS", "50"))
    DETECTION_CONFIDENCE: float = float(os.getenv("DETECTION_CONFIDENCE", "0.55"))
    COUNT_CONFIDENCE: float = float(os.getenv("COUNT_CONFIDENCE", "0.65"))
    MODEL_PATH: str = os.getenv("MODEL_PATH", "AI_MODEL/best.pt")


settings = Settings()

