from typing import Optional

CONTEXT_LABELS: dict[str, str] = {
    "grooming": "미용실",
    "hospital": "동물병원",
    "supplies": "용품점",
    "snack": "간식",
    "food": "사료",
    "clothes": "의류",
}


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
