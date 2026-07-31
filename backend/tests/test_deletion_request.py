import pytest
from sqlalchemy import select

from app.auth.models import DeletionRequest, Role, User
from app.auth.service import hash_password, seed_roles, seed_super_admin
from app.farms.models import Farm


@pytest.fixture(autouse=True)
def disable_rate_limit():
    from app.rate_limit import limiter

    limiter.enabled = False
    yield
    limiter.enabled = True


async def _seed_viewer(db_session, email="viewer@poultry.farm"):
    await seed_roles(db_session)
    await seed_super_admin(db_session)
    role_result = await db_session.execute(select(Role).where(Role.name == "viewer"))
    viewer_role = role_result.scalar_one()
    farm_result = await db_session.execute(select(Farm))
    farm = farm_result.scalars().first()
    viewer = User(
        email=email,
        hashed_password=hash_password("StrongPass1!"),
        full_name="Test Viewer",
        role_id=viewer_role.id,
        farm_id=farm.id,
        is_active=True,
    )
    db_session.add(viewer)
    await db_session.commit()
    return viewer


async def _login(client, email, password):
    response = await client.post("/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, f"Login failed: {response.status_code} {response.text[:300]}"
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_deletion_request_flow(client, db_session):
    viewer = await _seed_viewer(db_session)
    token = await _login(client, "viewer@poultry.farm", "StrongPass1!")

    response = await client.post(
        "/v1/auth/deletion-request",
        json={"reason": "No longer needed"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text

    await db_session.refresh(viewer)
    assert viewer.is_active is False

    result = await db_session.execute(select(DeletionRequest).where(DeletionRequest.user_id == viewer.id))
    deletion_request = result.scalar_one()
    assert deletion_request.status == "pending"
    assert deletion_request.reason == "No longer needed"
    assert deletion_request.email == "viewer@poultry.farm"

    login_again = await client.post("/v1/auth/login", json={
        "email": "viewer@poultry.farm",
        "password": "StrongPass1!",
    })
    assert login_again.status_code == 403

    from app.config import settings

    admin_token = await _login(client, "admin@poultry.farm", settings.default_admin_password)

    list_response = await client.get(
        "/v1/auth/deletion-requests",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert list_response.status_code == 200, list_response.text
    assert any(r["email"] == "viewer@poultry.farm" for r in list_response.json())

    approve_response = await client.post(
        f"/v1/auth/deletion-requests/{deletion_request.id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert approve_response.status_code == 204, approve_response.text

    result = await db_session.execute(select(User).where(User.id == viewer.id))
    assert result.scalar_one_or_none() is None

    await db_session.refresh(deletion_request)
    assert deletion_request.status == "completed"


@pytest.mark.asyncio
async def test_reject_deletion_request_reactivates_user(client, db_session):
    viewer = await _seed_viewer(db_session, email="reject@poultry.farm")
    token = await _login(client, "reject@poultry.farm", "StrongPass1!")

    response = await client.post(
        "/v1/auth/deletion-request",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text

    result = await db_session.execute(select(DeletionRequest).where(DeletionRequest.user_id == viewer.id))
    deletion_request = result.scalar_one()

    from app.config import settings

    admin_token = await _login(client, "admin@poultry.farm", settings.default_admin_password)
    reject_response = await client.post(
        f"/v1/auth/deletion-requests/{deletion_request.id}/reject",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert reject_response.status_code == 204, reject_response.text

    await db_session.refresh(viewer)
    assert viewer.is_active is True

    login_again = await client.post("/v1/auth/login", json={
        "email": "reject@poultry.farm",
        "password": "StrongPass1!",
    })
    assert login_again.status_code == 200


@pytest.mark.asyncio
async def test_super_admin_cannot_request_deletion(client, db_session):
    await _seed_viewer(db_session)
    from app.config import settings

    admin_token = await _login(client, "admin@poultry.farm", settings.default_admin_password)

    response = await client.post(
        "/v1/auth/deletion-request",
        json={"reason": "testing"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 400
    assert "super admin" in response.json()["detail"].lower()
