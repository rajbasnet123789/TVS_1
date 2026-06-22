import pytest
import uuid
from sqlalchemy import select
from app.cameras.models import Camera
from app.cameras.schemas import CameraUpdate
from app.cameras.service import update_camera


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "ok"}


@pytest.mark.asyncio
async def test_camera_roi_crud(db_session):
    # Setup test camera with ROI directly
    farm_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    roi = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
    camera = Camera(
        id=uuid.uuid4(),
        farm_id=farm_id,
        name="Test ROI Camera",
        rtsp_url="rtsp://example.com/stream",
        location="Barn 1",
        zone="East",
        roi=roi,
        enabled=True
    )
    db_session.add(camera)
    await db_session.commit()
    await db_session.refresh(camera)

    assert camera.roi == roi

    # Verify database state
    result = await db_session.execute(select(Camera).where(Camera.id == camera.id))
    db_camera = result.scalar_one()
    assert db_camera.roi == roi

    # 2. Update camera ROI via service update_camera function
    new_roi = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
    update_data = CameraUpdate(roi=new_roi)
    updated_camera = await update_camera(db_session, str(camera.id), update_data)
    assert updated_camera.roi == new_roi

    # 3. Update with empty/None ROI
    update_data_none = CameraUpdate(roi=None)
    updated_camera_none = await update_camera(db_session, str(camera.id), update_data_none)
    assert updated_camera_none.roi is None


@pytest.mark.asyncio
async def test_scan_results_filtering(client, db_session, monkeypatch):
    from app.auth.service import seed_roles, seed_super_admin
    from app.config import settings
    
    # 1. Seed admin and get authentication token
    await seed_roles(db_session)
    await seed_super_admin(db_session)
    await db_session.commit()
    
    response = await client.post("/v1/auth/login", json={
        "email": "admin@poultry.farm",
        "password": settings.default_admin_password,
    })
    assert response.status_code == 200
    token = response.json()["access_token"]
    
    # Set headers with a different farm_id than the existing camera's farm
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Farm-ID": "00000000-0000-0000-0000-000000000002"
    }
    
    # 2. Add Farm 2 and an existing camera directly to the DB under Farm 1
    from app.farms.models import Farm
    farm2 = Farm(
        id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        name="Farm 2",
        slug="farm-2",
        is_active=True
    )
    db_session.add(farm2)
    
    farm_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    camera = Camera(
        id=uuid.uuid4(),
        farm_id=farm_id,
        name="Existing Camera",
        rtsp_url="rtsp://192.168.1.100/live",
        enabled=True
    )
    db_session.add(camera)
    await db_session.commit()
    
    # 3. Mock the scan state with one existing and one new device
    mock_devices = [
        {"name": "Cam 1", "device_url": "http://192.168.1.100/onvif", "ip": "192.168.1.100", "xaddrs": "", "types": "", "scopes": ""},
        {"name": "Cam 2", "device_url": "http://192.168.1.101/onvif", "ip": "192.168.1.101", "xaddrs": "", "types": "", "scopes": ""}
    ]
    
    from app.cameras.router import _scan_state
    monkeypatch.setitem(_scan_state, "devices", mock_devices)
    
    # 4. Fetch scan results (with X-Farm-ID = Farm 2)
    results_resp = await client.get("/v1/cameras/scan/results", headers=headers)
    assert results_resp.status_code == 200
    results = results_resp.json()
    
    # Verify that the camera with IP 192.168.1.100 was filtered out globally, and only 192.168.1.101 remains
    assert len(results) == 1
    assert results[0]["ip"] == "192.168.1.101"

