from app.models.facility import PetFacility
from app.models.details import BusinessDetail, HospitalDetail


def test_pet_facility_tablename():
    assert PetFacility.__tablename__ == "pet_facilities"


def test_business_detail_tablename():
    assert BusinessDetail.__tablename__ == "business_details"


def test_hospital_detail_tablename():
    assert HospitalDetail.__tablename__ == "hospital_details"
