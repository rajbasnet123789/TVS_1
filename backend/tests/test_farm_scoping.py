import pytest
import uuid
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_camera_stats_wrong_farm_returns_404(client, db_session):
    from app.auth.service import seed_roles, seed_super_admin
    from app.config import settings
    from app.farms.models import Farm
    from app.cameras.models import Camera

    await seed_roles(db_session)
    await seed_super_admin(db_session)
    await db_session.commit()

    login = await client.post("/v1/auth/login", json={
        "email": "admin@poultry.farm",
        "password": settings.default_admin_password,
    })
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    farm2 = Farm(id=uuid.uuid4(), name="Farm 2", slug="farm-2", is_active=True)
    db_session.add(farm2)
    await db_session.commit()

    cam = Camera(id=uuid.uuid4(), name="F2 Cam", rtsp_url="rtsp://cam", farm_id=farm2.id)
    db_session.add(cam)
    await db_session.commit()

    headers2 = {"Authorization": f"Bearer {token}", "X-Farm-ID": str(uuid.uuid4())}
    resp = await client.get(f"/v1/cameras/{cam.id}/detection/stats", headers=headers2)
    assert resp.status_code == 404, "Should not find camera in wrong farm"


@pytest.mark.asyncio
async def test_camera_history_wrong_farm_returns_404(client, db_session):
    from app.auth.service import seed_roles, seed_super_admin
    from app.config import settings
    from app.cameras.models import Camera
    from app.farms.models import Farm

    await seed_roles(db_session)
    await seed_super_admin(db_session)
    await db_session.commit()

    login = await client.post("/v1/auth/login", json={
        "email": "admin@poultry.farm",
        "password": settings.default_admin_password,
    })
    token = login.json()["access_token"]

    farm = Farm(id=uuid.uuid4(), name="Test Farm", slug="test-farm", is_active=True)
    db_session.add(farm)
    await db_session.commit()

    cam = Camera(id=uuid.uuid4(), name="Cam", rtsp_url="rtsp://cam", farm_id=farm.id)
    db_session.add(cam)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {token}", "X-Farm-ID": str(uuid.uuid4())}
    resp = await client.get(f"/v1/cameras/{cam.id}/detection/history", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mcmt_identities_returns_global_results(client, db_session):
    from app.auth.service import seed_roles, seed_super_admin
    from app.config import settings

    await seed_roles(db_session)
    await seed_super_admin(db_session)
    await db_session.commit()

    login = await client.post("/v1/auth/login", json={
        "email": "admin@poultry.farm",
        "password": settings.default_admin_password,
    })
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/v1/detection/mcmt/identities", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_identities" in data
    assert "active_identities" in data


@pytest.mark.asyncio
async def test_mcmt_gallery_stats_returns(client, db_session):
    from app.auth.service import seed_roles, seed_super_admin
    from app.config import settings

    await seed_roles(db_session)
    await seed_super_admin(db_session)
    await db_session.commit()

    login = await client.post("/v1/auth/login", json={
        "email": "admin@poultry.farm",
        "password": settings.default_admin_password,
    })
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/v1/detection/mcmt/gallery/stats", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_embeddings" in data
    assert "embedding_dim" in data
    assert "active_count" in data


@pytest.mark.asyncio
async def test_alert_acknowledge_wrong_farm_returns_404(client, db_session):
    from app.auth.service import seed_roles, seed_super_admin
    from app.config import settings
    from app.alerts.models import Alert
    from app.farms.models import Farm

    await seed_roles(db_session)
    await seed_super_admin(db_session)
    await db_session.commit()

    login = await client.post("/v1/auth/login", json={
        "email": "admin@poultry.farm",
        "password": settings.default_admin_password,
    })
    token = login.json()["access_token"]

    farm = Farm(id=uuid.uuid4(), name="Test", slug="test", is_active=True)
    db_session.add(farm)
    await db_session.commit()

    alert = Alert(id=uuid.uuid4(), farm_id=farm.id, title="Test Alert", severity="info",
                  message="test", source="camera", is_acknowledged=False)
    db_session.add(alert)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {token}", "X-Farm-ID": str(uuid.uuid4())}
    resp = await client.put(f"/v1/alerts/{alert.id}/acknowledge", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_alert_rule_update_wrong_farm_returns_404(client, db_session):
    from app.auth.service import seed_roles, seed_super_admin
    from app.config import settings
    from app.alerts.models import AlertRule
    from app.farms.models import Farm

    await seed_roles(db_session)
    await seed_super_admin(db_session)
    await db_session.commit()

    login = await client.post("/v1/auth/login", json={
        "email": "admin@poultry.farm",
        "password": settings.default_admin_password,
    })
    token = login.json()["access_token"]

    farm = Farm(id=uuid.uuid4(), name="Test", slug="test", is_active=True)
    db_session.add(farm)
    await db_session.commit()

    rule = AlertRule(id=uuid.uuid4(), farm_id=farm.id, name="Test Rule",
                     metric="health_score", operator="lt", threshold=0.5)
    db_session.add(rule)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {token}", "X-Farm-ID": str(uuid.uuid4())}
    resp = await client.put(f"/v1/alerts/rules/{rule.id}", headers=headers, json={
        "name": "Hacked", "metric": "health_score", "operator": "lt", "threshold": 0.1
    })
    assert resp.status_code == 404
