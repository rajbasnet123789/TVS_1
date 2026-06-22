import os
from pathlib import Path
from dotenv import load_dotenv

# Load workspace root .env file
root_env = Path(__file__).resolve().parents[2] / ".env"
if root_env.exists():
    load_dotenv(root_env)

# Host connects to Postgres via port 5433 (mapped in docker-compose)
pg_pass = os.getenv("POSTGRES_PASSWORD", "poultry")
os.environ.setdefault("DATABASE_URL", f"postgresql+asyncpg://poultry:{pg_pass}@localhost:5433/poultry")

# Set dummy environment variables for tests before importing app config if still missing
os.environ.setdefault("POSTGRES_PASSWORD", pg_pass)
os.environ.setdefault("JWT_SECRET", "dummy_jwt_secret_value_for_testing_purposes")
os.environ.setdefault("INFLUX_TOKEN", "dummy_influx_token")
os.environ.setdefault("FRIGATE_API_URL", "http://localhost:5000")
os.environ.setdefault("MQTT_BROKER", "localhost")
os.environ.setdefault("MQTT_PORT", "1883")
os.environ.setdefault("ENCRYPTION_KEY", "dummy_encryption_key_value_for_testing_purposes")

import pytest
import pytest_asyncio
import asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings
from app.database import Base, get_db
import app.auth.models
import app.cameras.models
import app.chickens.models
import app.alerts.models
import app.farms.models

try:
    from app.main import app
except Exception:
    from fastapi import FastAPI
    app = FastAPI(title="TestFallback")
    app.dependency_overrides = {}

from sqlalchemy.pool import NullPool

pytest_plugins = ('pytest_asyncio',)

TEST_DATABASE_URL = settings.database_url

try:
    _test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
    TestingSessionLocal = async_sessionmaker(
        _test_engine, class_=AsyncSession, expire_on_commit=False
    )
except Exception:
    _test_engine = None
    TestingSessionLocal = None


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    db_ok = False
    if _test_engine is not None:
        try:
            async with _test_engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)
            db_ok = True
        except Exception:
            pass
    yield
    if db_ok:
        try:
            async with _test_engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await _test_engine.dispose()
        except Exception:
            pass

@pytest_asyncio.fixture
async def db_session():
    if _test_engine is None:
        pytest.skip("No database available")
        return
    try:
        conn = await _test_engine.connect()
    except Exception as e:
        pytest.skip(f"Database connection failed: {e}")
        return

    async with conn as connection:
        # First transaction to clean up any dirty database state
        clean_trans = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        from sqlalchemy import delete
        from app.alerts.models import Alert, AlertRule
        from app.cameras.models import Camera
        from app.chickens.models import Chicken
        from app.auth.models import User, Role
        from app.farms.models import Farm
        import uuid

        await session.execute(delete(Alert))
        await session.execute(delete(AlertRule))
        await session.execute(delete(Camera))
        await session.execute(delete(Chicken))
        await session.execute(delete(User))
        await session.execute(delete(Role))
        await session.execute(delete(Farm))
        
        # Add default farm
        default_farm = Farm(
            id=uuid.UUID('00000000-0000-0000-0000-000000000001'),
            name="Default Farm",
            slug="default",
            is_active=True
        )
        session.add(default_farm)
        await session.commit()
        await clean_trans.commit()
        await session.close()

        # Second transaction for the actual test execution (will be rolled back)
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        yield session
        await session.close()
        await transaction.rollback()

@pytest_asyncio.fixture(autouse=True)
async def mock_redis(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.data = {}
        async def setex(self, name, time, value):
            self.data[name] = value
        async def exists(self, name):
            return 1 if name in self.data else 0
        async def delete(self, name):
            self.data.pop(name, None)
        async def flushdb(self):
            self.data.clear()
        async def aclose(self):
            pass

    fake_r = FakeRedis()
    try:
        import app.auth.service as auth_service
        monkeypatch.setattr(auth_service, "redis_client", fake_r)
        monkeypatch.setattr(auth_service, "get_redis", lambda: fake_r)
    except Exception:
        pass
    yield fake_r

@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
