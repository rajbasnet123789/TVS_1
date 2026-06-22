import pytest
import pytest_asyncio
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from httpx import ASGITransport, AsyncClient

import app.health.queries
import app.alerts.rules
from app.auth.models import Role, User
from app.auth.service import create_access_token
from app.alerts.models import Alert, AlertRule
from app.cameras.models import Camera


class MockRecord:
    def __init__(self, time_val, values_dict, val):
        self.time_val = time_val
        self.values_dict = values_dict
        self.val = val

    def get_time(self):
        return self.time_val

    def get_value(self):
        return self.val

    @property
    def values(self):
        return self.values_dict


class MockTable:
    def __init__(self, records):
        self.records = records


class MockQueryApi:
    def __init__(self, tables_to_return):
        self.tables_to_return = tables_to_return
        self.queries_made = []

    def query(self, query, params=None):
        self.queries_made.append((query, params))
        return self.tables_to_return


class MockInfluxClient:
    def __init__(self, tables=None):
        self.query_api_mock = MockQueryApi(tables or [])

    def query_api(self):
        return self.query_api_mock


class MockSessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.fixture
def mock_influx(monkeypatch):
    client = MockInfluxClient()
    monkeypatch.setattr(app.health.queries, "_get_client", lambda: client)
    monkeypatch.setattr(app.alerts.rules, "_get_client", lambda: client)
    return client


@pytest_asyncio.fixture
async def auth_headers(db_session):
    # Create a viewer role if not exists
    res = await db_session.execute(select(Role).where(Role.name == "viewer"))
    role = res.scalar_one_or_none()
    if not role:
        role = Role(
            id=uuid.uuid4(),
            name="viewer",
            permissions=["dashboard:read"],
            description="Viewer role"
        )
        db_session.add(role)
        await db_session.commit()
        await db_session.refresh(role)

    # Create a user
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"test_viewer_{user_id}@poultry.farm",
        hashed_password="hashed_dummy",
        full_name="Test Viewer",
        role_id=role.id,
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = create_access_token(str(user.id), "viewer")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_unacknowledged_count(db_session):
    from app.alerts.service import get_unacknowledged_count

    # Verify count is 0
    count = await get_unacknowledged_count(db_session)
    assert count == 0

    # Add an unacknowledged alert
    alert1 = Alert(
        id=uuid.uuid4(),
        type="test_type",
        severity=1,
        message="Test alert 1",
    )
    db_session.add(alert1)
    await db_session.commit()

    count = await get_unacknowledged_count(db_session)
    assert count == 1

    # Add an acknowledged alert
    alert2 = Alert(
        id=uuid.uuid4(),
        type="test_type",
        severity=2,
        message="Test alert 2",
        acknowledged_at=datetime.now(timezone.utc),
    )
    db_session.add(alert2)
    await db_session.commit()

    count = await get_unacknowledged_count(db_session)
    assert count == 1


@pytest.mark.asyncio
async def test_health_scores_endpoint(client, auth_headers, mock_influx):
    time_now = datetime.now(timezone.utc)
    cam_id = str(uuid.uuid4())
    mock_record = MockRecord(
        time_val=time_now,
        values_dict={"camera_id": cam_id, "track_id": "10", "health_class": "normal"},
        val=85.5
    )
    mock_influx.query_api_mock.tables_to_return = [MockTable(records=[mock_record])]

    response = await client.get(f"/v1/health/scores?camera_id={cam_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["camera_id"] == cam_id
    assert data[0]["track_id"] == 10
    assert data[0]["health_class"] == "normal"
    assert data[0]["health_score"] == 85.5

    # Test with track_id = -1 (should map to None)
    mock_record_null = MockRecord(
        time_val=time_now,
        values_dict={"camera_id": cam_id, "track_id": "-1", "health_class": "normal"},
        val=85.5
    )
    mock_influx.query_api_mock.tables_to_return = [MockTable(records=[mock_record_null])]

    response = await client.get(f"/v1/health/scores?camera_id={cam_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["track_id"] is None


@pytest.mark.asyncio
async def test_health_summary_endpoint(client, auth_headers, mock_influx):
    mean_record = MockRecord(None, {}, 75.0)
    min_record = MockRecord(None, {}, 45.0)
    max_record = MockRecord(None, {}, 95.0)
    count_record = MockRecord(None, {}, 150)
    class_record1 = MockRecord(None, {"health_class": "normal"}, 120)
    class_record2 = MockRecord(None, {"health_class": "critical"}, 30)

    call_index = 0
    tables_sequence = [
        [MockTable(records=[mean_record])],
        [MockTable(records=[min_record])],
        [MockTable(records=[max_record])],
        [MockTable(records=[count_record])],
        [MockTable(records=[class_record1, class_record2])],
    ]

    def mock_query(query, params=None):
        nonlocal call_index
        res = tables_sequence[call_index]
        call_index = (call_index + 1) % len(tables_sequence)
        return res

    mock_influx.query_api_mock.query = mock_query

    response = await client.get("/v1/health/summary", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total_records"] == 150
    assert data["avg_health_score"] == 75.0
    assert data["min_health_score"] == 45.0
    assert data["max_health_score"] == 95.0
    assert data["class_distribution"] == {"normal": 120, "critical": 30}


@pytest.mark.asyncio
async def test_health_summary_no_data(client, auth_headers, mock_influx):
    mock_influx.query_api_mock.query = lambda query, params=None: []

    response = await client.get("/v1/health/summary", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total_records"] == 0
    assert data["avg_health_score"] == 0.0
    assert data["min_health_score"] is None
    assert data["max_health_score"] is None


@pytest.mark.asyncio
async def test_alert_rules_deduplication_inactivity(db_session, mock_influx, monkeypatch):
    from app.alerts.rules import _check_inactivity

    monkeypatch.setattr(app.alerts.rules, "async_session", lambda: MockSessionContext(db_session))

    camera = Camera(
        id=uuid.uuid4(),
        farm_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        name="Test Camera 1",
        rtsp_url="rtsp://localhost/stream1",
        enabled=True,
        status="online"
    )
    db_session.add(camera)
    await db_session.commit()

    mock_influx.query_api_mock.query = lambda query, params=None: []

    rule = AlertRule(
        name="Inactivity Warning",
        farm_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        metric="inactivity",
        operator=">",
        threshold=0,
        severity=1,
        duration_minutes=30
    )

    # First check: should create alert
    await _check_inactivity(rule)

    res = await db_session.execute(select(Alert).where(Alert.camera_id == camera.id))
    alerts = res.scalars().all()
    assert len(alerts) == 1
    assert alerts[0].type == "inactivity"
    assert "No chickens detected" in alerts[0].message

    # Second check: should NOT create duplicate alert
    await _check_inactivity(rule)
    res = await db_session.execute(select(Alert).where(Alert.camera_id == camera.id))
    alerts = res.scalars().all()
    assert len(alerts) == 1


@pytest.mark.asyncio
async def test_alert_rules_deduplication_health_critical(db_session, mock_influx, monkeypatch):
    from app.alerts.rules import _check_health_critical

    monkeypatch.setattr(app.alerts.rules, "async_session", lambda: MockSessionContext(db_session))

    camera = Camera(
        id=uuid.uuid4(),
        farm_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        name="Test Camera Critical",
        rtsp_url="rtsp://localhost/stream_crit",
        enabled=True,
        status="online"
    )
    db_session.add(camera)
    await db_session.commit()
    cam_id = str(camera.id)
    track_id = "42"

    record = MockRecord(
        time_val=datetime.now(timezone.utc),
        values_dict={"camera_id": cam_id, "track_id": track_id},
        val=25.0
    )
    mock_influx.query_api_mock.tables_to_return = [MockTable(records=[record])]

    rule = AlertRule(
        name="Health Critical",
        farm_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        metric="health_critical",
        operator="<",
        threshold=30,
        severity=2,
        duration_minutes=5
    )

    await _check_health_critical(rule)
    res = await db_session.execute(select(Alert).where(Alert.type == "health_critical"))
    alerts = res.scalars().all()
    assert len(alerts) == 1
    assert f"track {track_id}" in alerts[0].message

    await _check_health_critical(rule)
    res = await db_session.execute(select(Alert).where(Alert.type == "health_critical"))
    alerts = res.scalars().all()
    assert len(alerts) == 1


@pytest.mark.asyncio
async def test_alert_rules_deduplication_health_drop(db_session, mock_influx, monkeypatch):
    from app.alerts.rules import _check_health_drop

    monkeypatch.setattr(app.alerts.rules, "async_session", lambda: MockSessionContext(db_session))

    track_id = "55"

    def mock_query(query, params=None):
        if "start: -5m" in query:
            rec = MockRecord(None, {"track_id": track_id}, 50.0)
        else:
            rec = MockRecord(None, {"track_id": track_id}, 80.0)
        return [MockTable(records=[rec])]

    mock_influx.query_api_mock.query = mock_query

    rule = AlertRule(
        name="Health Drop",
        farm_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        metric="health_drop",
        operator=">",
        threshold=30,
        severity=1,
        duration_minutes=60
    )

    await _check_health_drop(rule)
    res = await db_session.execute(select(Alert).where(Alert.type == "health_drop"))
    alerts = res.scalars().all()
    assert len(alerts) == 1

    await _check_health_drop(rule)
    res = await db_session.execute(select(Alert).where(Alert.type == "health_drop"))
    alerts = res.scalars().all()
    assert len(alerts) == 1


@pytest.mark.asyncio
async def test_alert_rules_deduplication_missing_chicken(db_session, mock_influx, monkeypatch):
    from app.alerts.rules import _check_missing_chicken

    monkeypatch.setattr(app.alerts.rules, "async_session", lambda: MockSessionContext(db_session))

    track_id = "99"
    last_seen_time = datetime.now(timezone.utc) - timedelta(minutes=40)
    record = MockRecord(
        time_val=last_seen_time,
        values_dict={"track_id": track_id},
        val=1
    )
    mock_influx.query_api_mock.tables_to_return = [MockTable(records=[record])]

    rule = AlertRule(
        name="Missing Chicken",
        farm_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        metric="missing_chicken",
        operator=">",
        threshold=0,
        severity=2,
        duration_minutes=30
    )

    await _check_missing_chicken(rule)
    res = await db_session.execute(select(Alert).where(Alert.type == "missing_chicken"))
    alerts = res.scalars().all()
    assert len(alerts) == 1

    await _check_missing_chicken(rule)
    res = await db_session.execute(select(Alert).where(Alert.type == "missing_chicken"))
    alerts = res.scalars().all()
    assert len(alerts) == 1


@pytest.mark.asyncio
async def test_alert_rules_deduplication_camera_offline(db_session, monkeypatch):
    from app.alerts.rules import _check_camera_offline

    monkeypatch.setattr(app.alerts.rules, "async_session", lambda: MockSessionContext(db_session))

    camera = Camera(
        id=uuid.uuid4(),
        farm_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        name="Offline Camera",
        rtsp_url="rtsp://localhost/stream2",
        enabled=True,
        status="offline"
    )
    db_session.add(camera)
    await db_session.commit()

    rule = AlertRule(
        name="Camera Offline",
        farm_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        metric="camera_offline",
        operator=">",
        threshold=0,
        severity=1,
        duration_minutes=5
    )

    await _check_camera_offline(rule)
    res = await db_session.execute(select(Alert).where(Alert.camera_id == camera.id, Alert.type == "camera_offline"))
    alerts = res.scalars().all()
    assert len(alerts) == 1

    await _check_camera_offline(rule)
    res = await db_session.execute(select(Alert).where(Alert.camera_id == camera.id, Alert.type == "camera_offline"))
    alerts = res.scalars().all()
    assert len(alerts) == 1
