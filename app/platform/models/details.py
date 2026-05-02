from typing import Optional

from sqlalchemy import Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.platform.core.database import Base


class BusinessDetail(Base):
    __tablename__ = "business_details"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    facility_id: Mapped[int] = mapped_column(Integer, ForeignKey("pet_facilities.id", ondelete="CASCADE"), nullable=False)
    business_type: Mapped[str] = mapped_column(String(50), nullable=False)
    registration_no: Mapped[Optional[str]] = mapped_column(String(100))


class HospitalDetail(Base):
    __tablename__ = "hospital_details"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    facility_id: Mapped[int] = mapped_column(Integer, ForeignKey("pet_facilities.id", ondelete="CASCADE"), nullable=False)
    license_no: Mapped[Optional[str]] = mapped_column(String(100))
    specialty: Mapped[Optional[str]] = mapped_column(String(100))
