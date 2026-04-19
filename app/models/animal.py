from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, Date, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class AbandonedAnimal(Base):
    __tablename__ = "abandoned_animals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notice_no: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    animal_type: Mapped[Optional[str]] = mapped_column(String(20))
    breed: Mapped[Optional[str]] = mapped_column(String(100))
    age: Mapped[Optional[str]] = mapped_column(String(50))
    gender: Mapped[Optional[str]] = mapped_column(String(10))
    region: Mapped[Optional[str]] = mapped_column(String(100))
    shelter_name: Mapped[Optional[str]] = mapped_column(String(200))
    status: Mapped[Optional[str]] = mapped_column(String(30))
    notice_date: Mapped[Optional[datetime]] = mapped_column(Date)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
