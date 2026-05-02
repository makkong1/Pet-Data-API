from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.platform.core.database import Base


class PetFacility(Base):
    __tablename__ = "pet_facilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    address: Mapped[str] = mapped_column(String(300), nullable=False)
    region_city: Mapped[str] = mapped_column(String(50), nullable=False)
    region_district: Mapped[str] = mapped_column(String(50), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
