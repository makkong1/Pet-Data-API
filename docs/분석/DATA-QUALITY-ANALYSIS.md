# 데이터 품질 분석 — pet-data-api CLI JSON 출력

> 분석 날짜: 2026-05-27  
> 대상 파일: `~/data/pet-locations.json` (182건, 9개 컨텍스트)

---

## 1. 요약

| 지표 | 값 |
|------|----|
| 전체 레코드 수 | 182 |
| 주소(좌표) 있음 | 120 (65.9%) |
| 주소 없음 (노이즈) | **62 (34.1%)** |
| 중복 주소 | 0 (dedupe 정상) |
| Naver Local 보강된 비율 | ≈65.9% (주소 있는 행 = Naver Local title 적용) |
| 컨텍스트별 유효률 worst | pension 0%, restaurant 26% |

---

## 2. 컨텍스트별 품질 현황

| context | 전체 | 주소 있음 | 유효률 | 노이즈 수 |
|---------|------|----------|--------|----------|
| grooming | 23 | 22 | **96%** | 1 |
| hospital | 26 | 24 | **92%** | 2 |
| cafe | 50 | 37 | 74% | 13 |
| restaurant | 42 | 11 | **26%** | 31 |
| supplies | 17 | 9 | 53% | 8 |
| pension | 7 | 0 | **0%** | 7 |
| boarding | 5 | 5 | 100% | 0 |
| hotel | 6 | 6 | 100% | 0 |
| pharmacy | 6 | 6 | 100% | 0 |

> boarding·hotel은 `local_discovery` 경로(Naver Local 직접 검색)를 사용해 노이즈 없음.

---

## 3. 메트릭별 상세 분석

### Metric 1 — 주소/좌표 누락

- **62건(34.1%)** 이 주소와 좌표를 모두 갖지 않음.
- 이 행들은 Petory DB에 저장되더라도 지도 표시, 반경 검색에서 모두 제외됨 → **실질적으로 무가치한 데이터**.
- 컨텍스트 분포: restaurant 31건, cafe 13건, supplies 8건, pension 7건, hospital 2건, grooming 1건.

### Metric 2 — 노이즈 상호명

주소가 없는 62건의 name은 모두 실제 사업체명이 아닌 다음 유형 중 하나:

| 유형 | 예시 | 발생 컨텍스트 |
|------|------|-------------|
| 조사/종결어미 | 있는데, 이에요, 근데 | supplies, restaurant |
| 일반 명사/형용사 | 초대형, 모든, 입양, 길목, 큰골 | supplies, restaurant |
| 지역 묘사어 | 양양방향, 홍천대명, 오색, 경포몽 | cafe, pension |
| 인지 불가 복합어 | 쿠어드꾸드, 꽁냥꿍냥, 맛집까지 | cafe, restaurant |
| 실존 상호 추정이지만 Naver Local 미검색 | 노원더커피, 훌림목, 산내음 | cafe, restaurant |

### Metric 3 — 중복 주소

- **0건**: 동일 (name, address) 쌍 기준 dedupe 정상 작동.

### Metric 4 — Naver Local title 보강률

- 주소가 있는 120건(65.9%) = `enrich_with_location`이 Naver Local 결과를 찾아 title 덮어쓰기 성공.
- 주소가 없는 62건 = Naver Local 검색 실패 → blog 추출 키워드가 name으로 그대로 남음.
- **보강 성공 시 품질 대폭 향상**: grooming/hospital은 보강률 92~96%로 상호명이 실제 사업체명.

### Metric 5 — 컨텍스트 vs Naver Local 카테고리 일치율

JSON 레코드에 Naver Local 원본 카테고리가 저장되지 않아 직접 측정 불가.  
간접 지표 (보강 성공률):

- grooming/hospital: 96/92% → Naver Local가 해당 업종을 정확히 반환
- cafe: 74% → 카테고리는 맞으나 일부 소규모 카페가 Naver Local 미등록
- restaurant: 26% → **컨텍스트-업종 미스매치 심각**: 블로그에서 "반려동물 동반 맛집"으로 쓴 곳이 실제로는 고기집, 대게찜 등 일반 식당 (펫프렌들리 여부 불확실)
- pension: 0% → 블로그 글이 실제 펜션을 추천하는 게 아니라 강원도 여행 묘사 → 지역명이 상호명으로 추출됨

### Metric 6 — name+address 재검색 정확도 (추정)

라이브 Naver API 호출 없이 전수조사는 불가. 보강 성공 행 중 샘플링:

| name | address (일부) | 평가 |
|------|--------------|------|
| 마이뷰티독 신세계센텀시티부산점 | 부산 해운대구 센텀4로 | ✅ 실존 업체 |
| 피플앤독 | 부산 해운대구 | ✅ 실존 업체 |
| 코지로 아자스 이대 | 서울 서대문구 | ✅ 실존 업체 |
| 도그백 | 경기 성남시 | ✅ 실존 업체 |
| 산내음 | (no address) | ❌ 식당명 or 분위기 묘사어 |
| 경포몽 | (no address) | ❌ 경포대+꿈(경포몽) 지역 묘사어 |

---

## 4. 근본 원인 분석

### 4.1 restaurant — 74% 노이즈

**원인 1: `_MIN_MENTION_COUNT = 1`**  
1회 언급만으로도 후보가 되므로 블로그 1개에서 스쳐 지나간 식당명도 출력됨.

**원인 2: prefix 패턴 과포착**  
`반려동물 동반 가능한 ([상호명])` 패턴이 문장 끝 단어를 무조건 캡처:  
- "반려동물 동반 가능한 식당 정보" → "정보" 캡처 (blocklist에 있어 차단은 되나)
- "반려동물 동반 맛집 교리숯불갈비" → "교리숯불갈비" (유효처럼 보이나 실제 캡처 그룹은 blocklist 미포함 단어)
- "애견동반 야식맛집 맛닭꼬" → "맛닭꼬" (1회만 등장해도 통과)

**원인 3: 음식 카테고리 특성**  
반려동물 동반 식당 블로그 글은 장소 설명보다 '여행 스토리' 형식이 많아 상호명 밀도가 낮고, 맥락어("길목", "큰골", "차이들")가 name처럼 등장.

### 4.2 pension — 100% 노이즈

**원인: 블로그 콘텐츠 성격 불일치**  
"반려동물 펜션" 검색 결과는 펜션 후기가 아니라 **강원도/제주 여행 에세이**:  
"양양 해수욕장 앞 오색 펜션에서..." → "오색" 캡처  
"강릉 경포 인근 경포몽 펜션..." → "경포몽" 캡처 (지역+형용사 복합어)

실제 펜션 상호명은 suffix 패턴 `([상호명])펜션` 형식이 아닌 "OO 반려동물 펜션" 형식이 지배적이나 이 패턴은 현재 _PREFIX_PATTERNS에 없음.

### 4.3 cafe — 26% 노이즈

**원인: `_MIN_MENTION_COUNT = 1`**  
1회 언급 카페도 후보로 포함됨. Naver Local 미등록(소규모, 폐업, 이름 불일치) 카페는 address 없이 그대로 출력.

**보완 관찰**: "노원더커피", "훌림목" 등은 실존 가능성이 있으나 Naver Local에서 찾지 못함 → 이름 불일치 or 폐업.

### 4.4 supplies — 47% 노이즈

**원인: BLOCKLIST_EXACT 미등록 단어**  
- `초대형`, `모든`, `입양`, `이에요` → 명백히 상호명이 아니나 BLOCKLIST 없음
- `파밀리에드마스코`, `도그마루`, `도그원` → 실제 상호처럼 보이나 Naver Local 미검색 (이름 길거나 폐업)
- `있는데`, `이에요` → 어미형 패턴인데 `_GRAMMAR_ENDING` 정규식이 미탐지 (정규식은 1글자 어미만 체크)

---

## 5. 리팩토링 권고사항

### P0 — Post-enrichment 필터 (즉시 적용)

```python
# exporter.py collect_popular_for_cli() 내부
dtos = [popular_dict_to_dto(e, context) for e in deduped
        if e.get("road_address") or e.get("address")]  # ← 주소 없는 행 제거
```

효과: 62건 제거 → 120건으로 정리 (노이즈 0%)

### P1 — _MIN_MENTION_COUNT 조정

```python
_MIN_MENTION_COUNT: dict = {
    "grooming":   2,
    "hospital":   2,
    "supplies":   2,
    "pharmacy":   2,
    "cafe":       2,   # 1 → 2
    "pension":    2,
    "restaurant": 3,   # 1 → 3
    "boarding":   2,
    "hotel":      2,
}
```

### P2 — BLOCKLIST_EXACT 보강

```python
# 추가 대상
"초대형", "모든", "입양", "이에요",   # supplies 노이즈
"근데", "길목", "큰골", "차이들",     # restaurant 노이즈
"맛집까지",                          # restaurant 복합 노이즈
"경포", "양양", "홍천",              # 지역명 (LOCATION_CITY 미등록)
"오색", "경포몽",                    # pension 지역 묘사어
```

### P3 — _GRAMMAR_ENDING 정규식 확장

```python
# 현재: 1글자 어미만 탐지
# 추가: 복합 어미
_GRAMMAR_ENDING = re.compile(
    r"(?:인데|는데|있는데|이에요|예요|같아요|같아|이라|이라고|이고|했어|했어요|가요)$"
    r"|(?:한|는|된|인|을|를|이|가|도|만|서|로|와|과|며|고|어|아|해|게|에|의|은|다|던)$"
)
```

### P4 — pension 컨텍스트 처리

단기: `_LOCAL_DISCOVERY_CONTEXTS`에 pension 추가 → blog 추출 건너뛰고 Naver Local 직접 검색.  
장기: pension 컨텍스트 지원 여부 재검토 (반려동물 전용 펜션은 Naver Local 카테고리 미정립).

---

## 6. 구현 우선순위

| 우선순위 | 변경 | 기대 효과 |
|---------|------|----------|
| P0 | post-enrichment 주소 필터 | 즉시 노이즈 62건 제거, 180 → 120건 |
| P1 | MIN_MENTION_COUNT 조정 | restaurant/cafe 노이즈 감소 (다음 수집부터) |
| P2 | BLOCKLIST_EXACT 보강 | supplies 잔류 노이즈 제거 |
| P3 | GRAMMAR_ENDING 확장 | 복합 어미 노이즈 제거 |
| P4 | pension → local_discovery 전환 | pension 100% 노이즈 해결 |
