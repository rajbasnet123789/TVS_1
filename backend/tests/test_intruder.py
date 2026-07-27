import pytest
import numpy as np
import cv2
import uuid
import os
from unittest.mock import AsyncMock, MagicMock, patch

from app.detection.intruder import intruder_detector, FaceEmbedder, FaceGallery
from app.config import settings


@pytest.fixture(autouse=True)
def mock_face_embedder():
    """Mock the FaceEmbedder singleton to avoid initializing heavy neural networks in unit tests."""
    embedder_mock = MagicMock()
    # Return 1024-dimensional normalized float32 array
    dummy_emb = np.zeros(1024, dtype=np.float32)
    dummy_emb[0] = 1.0
    embedder_mock.extract.return_value = dummy_emb
    embedder_mock._loaded = True

    with patch.object(intruder_detector, "_embedder", embedder_mock):
        yield embedder_mock


def test_face_gallery_add_search_remove():
    # Initialize index-fallback FaceGallery
    gallery = FaceGallery(embedding_dim=1024, match_threshold=0.3)

    # 1. Gallery should be empty
    assert len(gallery.list_persons()) == 0

    # 2. Add a person
    emb_alice = np.zeros(1024, dtype=np.float32)
    emb_alice[0] = 1.0
    gallery.add("Alice", emb_alice)

    # Check Alice exists
    persons = gallery.list_persons()
    assert len(persons) == 1
    assert persons[0]["name"] == "Alice"

    # 3. Search Alice exact match
    match = gallery.search(emb_alice)
    assert match is not None
    assert match[0] == "Alice"
    assert match[1] >= 0.99

    # 4. Search Alice different embedding (orthogonal)
    emb_bob = np.zeros(1024, dtype=np.float32)
    emb_bob[1] = 1.0
    match_bob = gallery.search(emb_bob)
    assert match_bob is None

    # 5. Remove Alice
    assert gallery.remove("Alice") is True
    assert len(gallery.list_persons()) == 0


@pytest.mark.asyncio
async def test_intruder_config_and_gallery(client, db_session):
    from app.auth.service import seed_roles, seed_super_admin
    await seed_roles(db_session)
    await seed_super_admin(db_session)
    await db_session.commit()

    response = await client.post("/v1/auth/login", json={
        "email": "admin@poultry.farm",
        "password": settings.default_admin_password,
    })
    assert response.status_code == 200
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/v1/intruders/config", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["threshold"] == settings.intruder_threshold

    resp = await client.put("/v1/intruders/config", json={"threshold": 0.45}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["threshold"] == 0.45
    assert intruder_detector.gallery.threshold == 0.45

    resp = await client.get("/v1/intruders/gallery", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
