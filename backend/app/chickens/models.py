import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class Chicken(Base):
    __tablename__ = "chickens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    farm_id = Column(UUID(as_uuid=True), ForeignKey("farms.id"), nullable=False)
    chicken_id = Column(Integer, nullable=False)
    name = Column(String(100))
    breed = Column(String(100))
    status = Column(String(20), default="active")
    notes = Column(Text)
    global_id = Column(Integer, unique=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("farm_id", "chicken_id", name="uq_farm_chicken"),
    )
