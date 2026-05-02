from typing import Optional
import logging

CONTEXT_LABELS: dict[str, str] = {
    "grooming": "미용실",
    "hospital": "동물병원",
    "supplies": "용품점",
    "snack": "간식",
    "food": "사료",
    "clothes": "의류",
}

_log = logging.getLogger(__name__)


def build_prompt(
    context: str,
    facilities: list[dict],
    trends: list[dict],
    pet: Optional[dict],
) -> str:
    lines = []

    if pet:
        pet_type = pet.get("type", "")
        breed = pet.get("breed", "")
        age = pet.get("age", "")
        pet_desc = " ".join(filter(None, [breed, age, pet_type]))
        lines.append(f"- 반려동물: {pet_desc}")

    context_label = CONTEXT_LABELS.get(context, context)
    lines.append(f"- 찾는 서비스: {context_label}")

    if facilities:
        fac_desc = ", ".join(
            f"{f['name']}({f['distance_m']}m)" for f in facilities[:3]
        )
        lines.append(f"- 주변 시설 (가까운 순): {fac_desc}")
    else:
        lines.append("- 주변 시설 정보 없음")

    if trends:
        kw_desc = ", ".join(t["keyword"] for t in trends[:5])
        lines.append(f"- 요즘 인기 키워드: {kw_desc}")

    return "\n".join(lines) + "\n\n추천해줘."


def build_context_copy(
    context: str,
    facilities: list[dict],
    trends: list[tuple[str, int]],
    req_id: Optional[str] = None,
) -> Optional[str]:
    """컨텍스트 기반 규칙 추천 카피 (LLM 없음)."""
    rid = req_id or "-"
    context_label = CONTEXT_LABELS.get(context, context)

    if facilities:
        n = len(facilities)
        first = facilities[0]
        text = (
            f"근처 {n}개 {context_label} 후보를 찾았습니다. "
            f"가장 가까운 {first['name']}까지 {first['distance_m']}m입니다."
        )
        _log.info(
            "context_copy [%s] rule context=%s facilities=%d first_distance_m=%s",
            rid,
            context,
            n,
            first.get("distance_m"),
        )
        return text

    fallback = build_trend_only_copy(context, trends) or None
    _log.info(
        "context_copy [%s] trend_fallback context=%s trends=%d out_len=%s",
        rid,
        context,
        len(trends),
        len(fallback) if fallback else 0,
    )
    return fallback


def build_grooming_copy(
    facilities: list[dict],
    trends: list[tuple[str, int]],
    req_id: Optional[str] = None,
) -> Optional[str]:
    """하위 호환용 그루밍 전용 래퍼."""
    return build_context_copy("grooming", facilities, trends, req_id=req_id)


def build_trend_only_copy(context: str, trends: list[tuple[str, int]]) -> str:
    """시설 목록이 없고 트렌드만 있을 때(LLM 호출 없음). 키워드는 Redis에 저장된 네이버 집계 결과만 사용."""
    if not trends:
        return ""
    context_label = CONTEXT_LABELS.get(context, context)
    top = [k for k, _ in trends[:8]]
    kw = ", ".join(top)
    return (
        f"현재 좌표 반경에는 공공데이터에 등록된 {context_label}이(가) 없습니다. "
        f"블로그 검색으로 집계한 최근 인기 키워드는 {kw} 입니다. "
        f"실제 방문·예약은 지도·포털 검색과 후기를 함께 확인해 주세요."
    )
