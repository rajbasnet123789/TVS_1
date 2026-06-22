import os
import cv2
import numpy as np
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from app.auth.deps import require_permission, get_farm_id
from app.detection.intruder import intruder_detector
from app.config import settings

router = APIRouter(prefix="/intruders", tags=["intruders"])


class ConfigUpdate(BaseModel):
    threshold: float


def validate_farm_id(farm_id: str | None) -> str:
    if not farm_id:
        raise HTTPException(status_code=400, detail="farm_id is required")
    try:
        uuid.UUID(str(farm_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid farm ID format")
    return str(farm_id)


@router.get("/gallery")
async def get_gallery(
    user=Depends(require_permission("cameras:read")),
    farm_id: str = Depends(get_farm_id)
):
    farm_id = validate_farm_id(farm_id)
    gallery = intruder_detector.get_gallery(farm_id)
    return gallery.list_persons()


@router.post("/gallery/enroll")
async def enroll_person(
    name: str = Form(...),
    file: UploadFile = File(...),
    user=Depends(require_permission("cameras:write")),
    farm_id: str = Depends(get_farm_id)
):
    farm_id = validate_farm_id(farm_id)
    contents = await file.read()
    arr = np.frombuffer(contents, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    success = intruder_detector.enroll_person(name, frame, farm_id)
    if not success:
        raise HTTPException(status_code=400, detail="Could not detect or extract face from image")

    return {"status": "success", "message": f"Successfully enrolled {name}"}


@router.delete("/gallery/{name}")
async def delete_person(
    name: str,
    user=Depends(require_permission("cameras:write")),
    farm_id: str = Depends(get_farm_id)
):
    farm_id = validate_farm_id(farm_id)
    success = intruder_detector.remove_person(name, farm_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Person {name} not found in gallery")
    return {"status": "success", "message": f"Successfully removed {name}"}


@router.get("/config")
async def get_config(
    user=Depends(require_permission("cameras:read")),
    farm_id: str = Depends(get_farm_id)
):
    farm_id = validate_farm_id(farm_id)
    gallery = intruder_detector.get_gallery(farm_id)
    return {"threshold": gallery.threshold}


@router.put("/config")
async def update_config(
    data: ConfigUpdate,
    user=Depends(require_permission("settings:write")),
    farm_id: str = Depends(get_farm_id)
):
    farm_id = validate_farm_id(farm_id)
    if not (0.0 <= data.threshold <= 1.0):
        raise HTTPException(status_code=400, detail="Threshold must be between 0.0 and 1.0")

    gallery = intruder_detector.get_gallery(farm_id)
    gallery.threshold = data.threshold
    
    base_dir = os.path.dirname(settings.face_gallery_path)
    if os.path.isabs(base_dir):
        drive, path_tail = os.path.splitdrive(base_dir)
        base_dir = path_tail.lstrip("/\\")
    else:
        base_dir = base_dir.lstrip("/\\")

    filename = os.path.basename(settings.face_gallery_path)
    farm_gallery_path = os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
        base_dir,
        f"farm_{str(farm_id)}",
        filename
    )
    gallery.save(farm_gallery_path)

    return {"status": "success", "threshold": gallery.threshold}
