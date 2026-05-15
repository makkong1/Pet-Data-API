"""펫 매칭 신호 — 펫 종(species), 품종, 연령에 따른 룰 기반 적합도.

진짜 학습 모델이 아니라 데이터·서비스 신호가 모이기 전 가벼운 휴리스틱.
- 펫 species 키워드가 시설명·태그에 포함되면 가산.
- 노령(>=10살 키워드) 펫 + 컨텍스트=hospital 이면 가산 (병원이 노령 케어를 광고하면).
- 펫 정보 없으면 모두 0.
"""

from __future__ import annotations

import re
from typing import Optional

from sqlalchemy import text

from app.serving.recommender.signals.base import SignalContext, clamp01


_SPECIES_TOKENS: dict[str, list[str]] = {
    "dog": ["강아지", "개", "puppy", "dog"],
    "cat": ["고양이", "냥", "묘", "cat"],
    "rabbit": ["토끼", "rabbit"],
}

_SENIOR_PATTERN = re.compile(r"(\d+)\s*살|(\d+)\s*세|senior", re.IGNORECASE)


def _is_senior(age_text: str) -> bool:
    if not age_text:
        return False
    m = _SENIOR_PATTERN.search(age_text)
    if not m:
        return False
    n = m.group(1) or m.group(2)
    if n is None:
        # 'senior' 단어로 매칭된 경우.
        return True
    try:
        return int(n) >= 10
    except ValueError:
        return False


class PetMatchSignal:
    name = "pet_match"

    def __init__(self) -> None:
        self._tag_cache: dict[int, set[str]] = {}

    async def _load_tags(self, ctx: SignalContext, facility_ids: list[int]) -> None:
        if ctx.db is None or not facility_ids:
            return
        try:
            result = await ctx.db.execute(
                text(
                    "SELECT facility_id, tag FROM facility_tags "
                    "WHERE facility_id = ANY(:fids)"
                ),
                {"fids": facility_ids},
            )
            for row in result.mappings().all():
                self._tag_cache.setdefault(int(row["facility_id"]), set()).add(
                    str(row["tag"]).lower()
                )
        except Exception:
            return

    async def score(self, candidates: list[dict], ctx: SignalContext) -> list[float]:
        self._tag_cache.clear()
        if not candidates or not ctx.pet:
            return [0.0] * len(candidates)

        species = (ctx.pet.get("type") or "").lower()
        breed = (ctx.pet.get("breed") or "").lower()
        age = ctx.pet.get("age") or ""
        senior = _is_senior(age)
        species_tokens = _SPECIES_TOKENS.get(species, [])

        facility_ids = [
            int(c["facility_id"]) for c in candidates if c.get("facility_id") is not None
        ]
        await self._load_tags(ctx, facility_ids)

        out: list[float] = []
        for c in candidates:
            s = 0.0
            name_lc = (c.get("name") or "").lower()
            tags = self._tag_cache.get(int(c["facility_id"]), set()) if c.get("facility_id") else set()

            for tok in species_tokens:
                if tok in name_lc or tok in tags:
                    s = max(s, 0.6)
                    break
            if breed and (breed in name_lc or breed in tags):
                s = max(s, 0.8)
            if senior and ctx.context == "hospital":
                for senior_tok in ("노령", "노견", "노묘", "senior"):
                    if senior_tok in name_lc or senior_tok in tags:
                        s = max(s, 0.9)
                        break
            out.append(clamp01(s))
        return out

    def reason_label(self, candidate: dict, candidate_score: float) -> Optional[str]:
        if candidate_score >= 0.7:
            return "pet_breed_match"
        if candidate_score >= 0.4:
            return "pet_species_match"
        return None
