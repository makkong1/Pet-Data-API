"""
상호명 추출 품질 테스트 — 근본 원인 기반.

근본 원인:
1. PREFIX 패턴이 업종 키워드 뒤에 오는 아무 단어(조사, 약품명, 직책)를 캡처
2. SUFFIX 패턴이 지역명+행정구+동물 복합어를 구분 못함
3. '반려' 포함 복합어(창원반려)가 지역+일반명사 조합임에도 통과
"""
import pytest
from app.ingestion.blog import _extract_candidates_from_text, _is_valid_name


# ── Phase 1 실패 케이스 (구조적 근본 원인) ─────────────────────────────

class TestPrefixPatternNoise:
    """PREFIX 패턴이 비상호명 단어를 캡처하는 구조적 문제."""

    def test_boarding_prefix_no_particle(self):
        """위탁관리/호텔링 뒤 조사가 후보로 추출되면 안 됨."""
        text = "반려동물 호텔링까지 제공해요 위탁관리이나 맡길 수 있어요"
        cands = _extract_candidates_from_text(text, "boarding")
        assert "까지" not in cands
        assert "이나" not in cands

    def test_boarding_prefix_no_service_word(self):
        """위탁관리 뒤 서비스 등 일반명사가 후보로 추출되면 안 됨."""
        text = "반려동물 호텔링서비스 전문 위탁관리센터"
        cands = _extract_candidates_from_text(text, "boarding")
        assert "서비스" not in cands

    def test_pharmacy_prefix_no_drug_name(self):
        """동물약국 뒤 약품명이 후보로 추출되면 안 됨."""
        text = "반려동물약국 넥스가드 처방 동물약국에서 스펙트라 구매했어요"
        cands = _extract_candidates_from_text(text, "pharmacy")
        assert "넥스가드" not in cands
        assert "스펙트라" not in cands

    def test_hospital_prefix_no_job_title(self):
        """동물병원 뒤 직책명이 후보로 추출되면 안 됨."""
        text = "동물병원 코디네이터 연락처 동물병원 원장님께"
        cands = _extract_candidates_from_text(text, "hospital")
        assert "코디네이터" not in cands
        assert "원장님께" not in cands


class TestSuffixPatternNoise:
    """SUFFIX 패턴의 복합어 캡처 문제."""

    def test_grooming_no_location_district_compound(self):
        """지역명+행정구+동물 복합어가 추출되면 안 됨."""
        text = "울산동구애견미용실 후기 울산동구 애견미용"
        cands = _extract_candidates_from_text(text, "grooming")
        assert "울산동구애견" not in cands

    def test_no_companion_animal_prefix_compound(self):
        """지역명+반려 복합어(창원반려)가 pharmacy에서 추출되면 안 됨."""
        text = "창원반려동물약국 이용했어요"
        cands = _extract_candidates_from_text(text, "pharmacy")
        assert "창원반려" not in cands


# ── 정상 상호명은 추출되어야 함 ────────────────────────────────────────

class TestValidBusinessExtraction:
    """실제 상호명이 정상 추출되는지 확인."""

    def test_grooming_suffix_extracts_real_name(self):
        text = "소담애견미용실 다녀왔어요 정말 좋았어요"
        cands = _extract_candidates_from_text(text, "grooming")
        assert "소담애견" in cands

    def test_hospital_suffix_extracts_real_name(self):
        text = "이오동물병원 진료 후기입니다"
        cands = _extract_candidates_from_text(text, "hospital")
        assert "이오" in cands

    def test_pharmacy_suffix_extracts_real_name(self):
        text = "평택녹십자동물약국에서 처방받았어요"
        cands = _extract_candidates_from_text(text, "pharmacy")
        assert "평택녹십자" in cands

    def test_hotel_suffix_extracts_real_name(self):
        text = "키녹펫호텔 이용 후기"
        cands = _extract_candidates_from_text(text, "hotel")
        assert "키녹" in cands


# ── _is_valid_name 필터 단위 테스트 ───────────────────────────────────

class TestIsValidName:

    def test_district_compound_blocked(self):
        assert not _is_valid_name("울산동구애견")
        assert not _is_valid_name("부산서구병원")
        assert not _is_valid_name("대전남구샵")

    def test_companion_prefix_compound_blocked(self):
        assert not _is_valid_name("창원반려")
        assert not _is_valid_name("부산반려")

    def test_real_names_pass(self):
        assert _is_valid_name("이오")
        assert _is_valid_name("더휴")
        assert _is_valid_name("평택녹십자")
        assert _is_valid_name("소담")
        assert _is_valid_name("오션시티")
        assert _is_valid_name("키녹")
