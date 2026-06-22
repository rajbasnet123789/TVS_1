import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test_jwt_secret")
os.environ.setdefault("INFLUX_TOKEN", "test_influx_token")
os.environ.setdefault("ENCRYPTION_KEY", "test_encryption_key_32_bytes_long!")
os.environ.setdefault("FRIGATE_API_URL", "http://localhost:5000")
os.environ.setdefault("MQTT_BROKER", "localhost")
os.environ.setdefault("MQTT_PORT", "1883")

import pytest
