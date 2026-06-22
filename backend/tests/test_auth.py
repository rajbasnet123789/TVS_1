import pytest
from app.auth.service import seed_roles, seed_super_admin, hash_password
from sqlalchemy import select
from app.auth.models import User, Role


@pytest.mark.asyncio
async def test_login_invalid_credentials(client):
    response = await client.post("/v1/auth/login", json={
        "email": "nonexistent@poultry.farm",
        "password": "wrongpass1A!",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_success_with_seeded_admin(client, db_session):
    """Seed roles + admin, then login with the configured password."""
    from app.config import settings

    await seed_roles(db_session)
    await seed_super_admin(db_session)
    await db_session.commit()

    from app.auth.service import verify_password
    result = await db_session.execute(select(User).where(User.email == "admin@poultry.farm"))
    user = result.scalar_one_or_none()
    assert user is not None
    assert verify_password(settings.default_admin_password, user.hashed_password)

    response = await client.post("/v1/auth/login", json={
        "email": "admin@poultry.farm",
        "password": settings.default_admin_password,
    })
    assert response.status_code == 200, f"Login failed: {response.status_code} {response.text[:300]}"
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"

    token = body["access_token"]
    me_resp = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "admin@poultry.farm"


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_register_requires_auth(client):
    response = await client.post("/v1/auth/register", json={
        "email": "new@poultry.farm",
        "password": "StrongPass1!",
        "full_name": "New User",
        "role_name": "viewer",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_with_invalid_token(client):
    response = await client.post("/v1/auth/refresh", json={
        "refresh_token": "invalid_token_here",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_requires_auth(client):
    response = await client.post("/v1/auth/logout")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_me_unauthenticated(client):
    response = await client.get("/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_config(client):
    from app.config import settings
    original_id = settings.google_client_id
    settings.google_client_id = "test-google-client-id"
    try:
        response = await client.get("/v1/auth/config")
        assert response.status_code == 200
        assert response.json()["google_client_id"] == "test-google-client-id"
    finally:
        settings.google_client_id = original_id


@pytest.mark.asyncio
async def test_google_login_not_configured(client):
    from app.config import settings
    original_id = settings.google_client_id
    settings.google_client_id = ""
    try:
        response = await client.post("/v1/auth/google", json={"credential": "some_token"})
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"].lower()
    finally:
        settings.google_client_id = original_id


@pytest.mark.asyncio
async def test_google_login_success(client, db_session, monkeypatch):
    import httpx
    from app.config import settings
    from app.auth.service import seed_roles, seed_super_admin
    
    monkeypatch.setattr(settings, "google_client_id", "test-google-client-id")
    await seed_roles(db_session)
    await seed_super_admin(db_session)
    await db_session.commit()
    
    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json_data = json_data

        def json(self):
            return self._json_data

    async def mock_get(self_client, url, params=None, **kwargs):
        assert url == "https://oauth2.googleapis.com/tokeninfo"
        assert params == {"id_token": "valid_token"}
        return MockResponse(200, {
            "aud": "test-google-client-id",
            "email_verified": "true",
            "email": "admin@poultry.farm"
        })
        
    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
    
    response = await client.post("/v1/auth/google", json={"credential": "valid_token"})
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_google_login_failures(client, db_session, monkeypatch):
    import httpx
    from app.config import settings
    from app.auth.service import seed_roles, seed_super_admin
    
    monkeypatch.setattr(settings, "google_client_id", "test-google-client-id")
    await seed_roles(db_session)
    await seed_super_admin(db_session)
    await db_session.commit()
    
    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json_data = json_data

        def json(self):
            return self._json_data

    async def mock_get(self_client, url, params=None, **kwargs):
        assert url == "https://oauth2.googleapis.com/tokeninfo"
        token = params.get("id_token")
        if token == "mismatch_token":
            return MockResponse(200, {
                "aud": "wrong-client-id",
                "email_verified": "true",
                "email": "admin@poultry.farm"
            })
        elif token == "unverified_token":
            return MockResponse(200, {
                "aud": "test-google-client-id",
                "email_verified": "false",
                "email": "admin@poultry.farm"
            })
        elif token == "not_found_token":
            return MockResponse(200, {
                "aud": "test-google-client-id",
                "email_verified": "true",
                "email": "notfound@poultry.farm"
            })
        elif token == "invalid_token":
            return MockResponse(400, {"error": "invalid_token"})
        return MockResponse(400, {})
        
    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
    
    # 1. Audience mismatch
    response = await client.post("/v1/auth/google", json={"credential": "mismatch_token"})
    assert response.status_code == 401
    assert "audience mismatch" in response.json()["detail"].lower()
    
    # 2. Email unverified
    response = await client.post("/v1/auth/google", json={"credential": "unverified_token"})
    assert response.status_code == 401
    assert "email is not verified" in response.json()["detail"].lower()
    
    # 3. Account not found (not in database)
    response = await client.post("/v1/auth/google", json={"credential": "not_found_token"})
    assert response.status_code == 404
    assert "account not found" in response.json()["detail"].lower()
    
    # 4. Invalid Google credential (HTTP error from google)
    response = await client.post("/v1/auth/google", json={"credential": "invalid_token"})
    assert response.status_code == 401
    assert "failed to verify" in response.json()["detail"].lower() or "invalid google credential" in response.json()["detail"].lower()

