import logging
import os
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


def _read_secret_file(path_env_var: str) -> str | None:
    path = os.environ.get(path_env_var)
    if path and os.path.exists(path):
        try:
            with open(path, "r") as f:
                return f.read().strip()
        except Exception as e:
            logger.error("Error reading secret file from environment variable %s (path: %s): %s", path_env_var, path, e)
    return None


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://poultry:poultry@localhost:5432/poultry"
    redis_url: str = "redis://localhost:6379/0"
    influx_url: str = "http://localhost:8086"
    influx_token: str = ""
    influx_org: str = "poultry"
    influx_bucket: str = "detections"
    media_root: str = "/var/opt/poultry/media"
    frigate_api_url: str = "http://frigate:5000"
    frigate_go2rtc_url: str = "http://frigate:1984"
    mqtt_broker: str = "mosquitto"
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    encryption_key: str = ""
    encryption_salt: str = ""
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    cors_origins: str = "http://localhost:3000"
    log_level: str = "WARNING"
    db_echo: bool = False
    model_health_path: str = ""
    model_health_checksum_sha256: str = ""
    camera_process_interval: int = 3
    cookies_secure: bool = False
    postgres_password: str = ""
    default_admin_password: str = ""
    debug: bool = True
    environment: str = "development"
    sentry_dsn: str = ""
    google_client_id: str = ""
    nvr_host: str = ""
    nvr_username: str = ""
    nvr_password: str = ""
    intruder_threshold: float = 0.3
    face_gallery_path: str = "known_persons/embeddings.json"

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore", "protected_namespaces": ()}

    def __init__(self, **values):
        super().__init__(**values)
        for field, file_env in [
            ("postgres_password", "POSTGRES_PASSWORD_FILE"),
            ("influx_token", "INFLUX_TOKEN_FILE"),
            ("encryption_key", "ENCRYPTION_KEY_FILE"),
            ("encryption_salt", "ENCRYPTION_SALT_FILE"),
            ("jwt_secret", "JWT_SECRET_FILE"),
            ("default_admin_password", "DEFAULT_ADMIN_PASSWORD_FILE"),
            ("nvr_password", "NVR_PASSWORD_FILE"),
            ("mqtt_username", "MQTT_USERNAME_FILE"),
            ("mqtt_password", "MQTT_PASSWORD_FILE"),
        ]:
            val = _read_secret_file(file_env)
            if val:
                setattr(self, field, val)


settings = Settings()

if not settings.default_admin_password:
    raise ValueError("DEFAULT_ADMIN_PASSWORD environment variable is required")
if not settings.postgres_password:
    raise ValueError("POSTGRES_PASSWORD environment variable is required")
if not settings.jwt_secret:
    raise ValueError(
        "JWT_SECRET environment variable is required — "
        "generate with: openssl rand -hex 32"
    )
if not settings.influx_token:
    raise ValueError("INFLUX_TOKEN environment variable is required")
if not settings.encryption_key:
    raise ValueError(
        "ENCRYPTION_KEY environment variable is required — "
        "generate with: openssl rand -hex 32"
    )
if not settings.encryption_salt:
    raise ValueError(
        "ENCRYPTION_SALT environment variable is required — "
        "generate with: openssl rand -hex 32"
    )
