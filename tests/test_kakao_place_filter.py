from app.ingestion.kakao import _build_query, _is_pet_related_doc


def test_build_query_appends_grooming_hint():
    assert _build_query("멍멍샵") == "멍멍샵 애견미용"


def test_is_pet_related_doc_true():
    doc = {
        "place_name": "멍멍샵",
        "category_name": "서비스,산업 > 애완동물 > 애완동물미용",
    }
    assert _is_pet_related_doc(doc) is True


def test_is_pet_related_doc_false_for_unrelated_place():
    doc = {
        "place_name": "세월호 기억공간 기억과빛",
        "category_name": "문화시설 > 전시관",
    }
    assert _is_pet_related_doc(doc) is False
