import pytest
import tempfile
import os
from pathlib import Path


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.config.settings.media_root", str(tmp_path))
    monkeypatch.setattr("app.media.client.MEDIA_ROOT", None)


@pytest.mark.asyncio
async def test_put_and_get_object():
    from app.media.client import put_object, get_object
    data = b"hello-world-image-data"
    key = await put_object("farm-1", "snapshots/cam1/test.jpg", data, "image/jpeg")
    assert key == "snapshots/cam1/test.jpg"

    retrieved = await get_object("farm-1", "snapshots/cam1/test.jpg")
    assert retrieved == data


@pytest.mark.asyncio
async def test_get_object_not_found():
    from app.media.client import get_object
    data = await get_object("farm-1", "nonexistent.jpg")
    assert data is None


@pytest.mark.asyncio
async def test_delete_object():
    from app.media.client import put_object, delete_object, get_object
    await put_object("farm-2", "test/delete_me.txt", b"delete-me")
    assert await get_object("farm-2", "test/delete_me.txt") == b"delete-me"

    result = await delete_object("farm-2", "test/delete_me.txt")
    assert result is True
    assert await get_object("farm-2", "test/delete_me.txt") is None


@pytest.mark.asyncio
async def test_delete_object_not_found():
    from app.media.client import delete_object
    result = await delete_object("farm-1", "ghost.txt")
    assert result is False


@pytest.mark.asyncio
async def test_list_objects():
    from app.media.client import put_object, list_objects
    await put_object("farm-3", "a/1.txt", b"a1")
    await put_object("farm-3", "a/2.txt", b"a2")
    await put_object("farm-3", "b/3.txt", b"b3")

    items = await list_objects("farm-3")
    assert items == ["a/1.txt", "a/2.txt", "b/3.txt"]


@pytest.mark.asyncio
async def test_list_objects_with_prefix():
    from app.media.client import put_object, list_objects
    await put_object("farm-4", "snapshots/cam1/a.jpg", b"a")
    await put_object("farm-4", "snapshots/cam2/b.jpg", b"b")
    await put_object("farm-4", "other/c.txt", b"c")

    items = await list_objects("farm-4", prefix="snapshots")
    assert items == ["snapshots/cam1/a.jpg", "snapshots/cam2/b.jpg"]


@pytest.mark.asyncio
async def test_farm_isolation():
    from app.media.client import put_object, get_object
    await put_object("farm-a", "shared.txt", b"farm-a-data")
    await put_object("farm-b", "shared.txt", b"farm-b-data")

    assert await get_object("farm-a", "shared.txt") == b"farm-a-data"
    assert await get_object("farm-b", "shared.txt") == b"farm-b-data"


@pytest.mark.asyncio
async def test_farm_prefix_requires_value():
    from app.media.client import put_object
    with pytest.raises(ValueError, match="farm_id is required"):
        await put_object("", "test.txt", b"data")


@pytest.mark.asyncio
async def test_media_upload_requires_auth(client, db_session):
    response = await client.post("/v1/media/upload", files={"file": ("test.jpg", b"data")})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_media_list_requires_auth(client, db_session):
    response = await client.get("/v1/media/list")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_media_download_requires_auth(client, db_session):
    response = await client.get("/v1/media/download/snapshots/cam1/test.jpg")
    assert response.status_code == 401
