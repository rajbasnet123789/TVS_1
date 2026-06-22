import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    farm_id = Column(UUID(as_uuid=True), ForeignKey("farms.id"), nullable=False)
    coop_id = Column(UUID(as_uuid=True), ForeignKey("coops.id"), nullable=True)
    name = Column(String(100), nullable=False)
    rtsp_url = Column(String(500), nullable=False)
    location = Column(String(100))
    zone = Column(String(50))
    status = Column(String(20), default="offline")
    fps_target = Column(Integer, default=5)
    resolution_width = Column(Integer, default=1920)
    resolution_height = Column(Integer, default=1080)
    username = Column(String(100))
    password_hash = Column(String(255))
    enabled = Column(Boolean, default=True)
    pos_x = Column(Integer, default=0)
    pos_y = Column(Integer, default=0)
    pos_z = Column(Integer, default=0)
    snapshot_url = Column(String(500), nullable=True)
    roi = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


