from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://poultry:poultry@localhost:5432/poultry"
    redis_url: str = "redis://localhost:6379/0"
    influx_url: str = "http://localhost:8086"
    influx_token: str = "dev-token-change-me"
    influx_org: str = "poultry"
    influx_bucket: str = "detections"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "poultry-media"
    mediamtx_api_url: str = "http://localhost:9997"
    mediamtx_api_user: str = "admin"
    mediamtx_api_pass: str = "admin123"
    jwt_secret: str = "dev-secret-change-in-production-min-32-chars"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    cors_origins: str = "http://localhost:3000"
    onvif_scan_subnet: str = "192.168.1.0/24"
    log_level: str = "DEBUG"

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
