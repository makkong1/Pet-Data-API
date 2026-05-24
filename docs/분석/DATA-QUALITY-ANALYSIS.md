# 데이터 품질 분석 — Popular·Trends 파이프라인

> 작성일: 2026-05-24  
> 대상: `app/ingestion/blog.py`, `app/ingestion/analyzer/morpheme.py`

---

## 1. 파이프라인 구조 요약

### Popular (인기 상호명)

```text
네이버 블로그 + 카페 검색
    → 제목·설명 텍스트에서 정규식 패턴으로 상호 후보 추출
    → MIN_MENTION_COUNT ≥ 2 필터
    → freshness 가중 점수화
    → Redis JSON (popular:{context})
```

핵심 코드: `app/ingestion/blog.py`  
패턴 위치: `_SUFFIX_PATTERNS`, `_PREFIX_PATTERNS`  
필터 위치: `_BLOCKLIST_EXACT`, `_BLOCKLIST_CONTAINS`, `_LOCATION_CITY`, `_GRAMMAR_ENDING`

### Trends (트렌드 키워드)

```text
네이버 블로그 + 카페 검색
    → kiwipiepy 형태소 분석 (NNG·NNP만 추출)
    → STOPWORDS 필터
    → Counter 집계
    → Redis Sorted Set (trends:{category}:keywords)
```

핵심 코드: `app/ingestion/analyzer/morpheme.py`, `app/ingestion/analyzer/trend.py`

---

## 2. 관찰된 증상 (2026-05-24 초기 배치 결과)

### Popular

```text
popular/cafe:   in_cache=3, sample=['온독', '바닐라브릭', '진짜']
popular/pension: in_cache=16, sample=['내돈내산', '포천', '쓰담쓰담', '주소', '이라', ...]
popular/boarding: in_cache=2, sample=['와요', '전원주택']
popular/hotel:  in_cache=4, sample=['키녹', '더위크앤리조트', '부터', ...]
```

### Trends (cafe 기준)

```text
('맛집',124), ('커피',115), ('공간',107), ('대형',103), ('실내',99), ('분위기',80), ('야외',72)
```

---

## 3. 근본 원인 분석

### 3-1. 패턴과 실제 데이터 불일치 (Recall 저하)

**설계 가정**: 한국어 상호명은 `[상호명]+[업종]` suffix 형식  
→ `_SUFFIX_PATTERNS["cafe"]`: `([가-힣a-zA-Z0-9]{2,10})\s*(?:애견카페|반려동물카페|펫카페)`

**실제 데이터** (SQLite `raw_posts` 샘플):

```text
반려동물 동반 카페 노원더커피          ← 키워드 뒤에 상호
반려동물 동반 가능한 천리카페          ← 가능한 뒤에 상호
반려동물동반카페 '몽킽' 일산밤리단길   ← 키워드 바로 뒤 상호
반려동물 동반 가능한 인스밀            ← 업종명 없이 상호만
```

suffix 패턴(`[상호명]애견카페`)은 실제로 거의 쓰이지 않는 형식.  
→ 989개 포스트에서 후보 추출 228개, MIN_MENTION_COUNT=2 통과 **2개**.

**업종별 recall 현황** (2026-05-24 마지막 배치):

| 컨텍스트 | unique_posts | candidates | count(Redis) | 비고 |
|---------|-------------|-----------|-------------|------|
| grooming | ~1000 | ~300+ | 20 | suffix 패턴 잘 맞음 |
| hospital | ~900 | ~300+ | 20 | suffix 패턴 잘 맞음 |
| cafe | 989 | 228 | 2 | 패턴 불일치 |
| pension | 758 | 157 | 12 | 중간 수준 |
| boarding | 993 | 83 | 0 | 구조적 한계 (아래 참조) |
| hotel | 942 | 170 | 3 | 패턴 부분 불일치 |

### 3-2. 업종별 포스트 특성 불균형 (Boarding 0건)

boarding 포스트 특성:

- 위탁 창업 가이드, 마케팅 컨텐츠, 서비스 비교 글 위주
- 특정 업체명이 2회 이상 반복 등장하는 포스트 거의 없음
- 현재 suffix 패턴(`[상호명]위탁관리|호텔링센터|펫시터`)이 실제 등장 빈도 낮음

→ 패턴 추가로 해결 불가. **쿼리 전략 자체 변경 필요** (예: 업체명 특화 쿼리).

### 3-3. 카페 API 합류 후 범용어 볼륨 증가 (Trends Noise)

2026-05-24 배치부터 네이버 카페(`cafearticle.json`) 병합 시작.

카페 글의 특성:

- 펫 전문 블로그가 아닌 일상 커뮤니티 글 혼입
- "반려동물 동반 가능한 대형 카페" → '대형', '실내', '야외', '공간', '분위기'
- "신형 교환기", "아파트 단지 내 카페" → '교환기', '아파트'

blogyonly 시절에는 펫 특화 필자가 많아 이런 범용어가 하위권에 머물렀으나,  
카페 합류 후 볼륨이 증폭되어 상위권 진입.

### 3-4. MIN_MENTION_COUNT와 Recall 트레이드오프

현재 설정: `_MIN_MENTION_COUNT = 2`

| 임계값 | 효과 |
|-------|------|
| 1 | count 증가, 1회 언급 노이즈도 통과 |
| 2 (현재) | 노이즈 감소, cafe/boarding count 낮음 |
| 3 | 노이즈 최소, 대부분 카테고리 count 급감 |

→ 임계값 조정은 마지막 수단. **패턴 recall 개선이 우선**.

### 3-5. BLOCKLIST Exact vs Contains 설계 한계

`_BLOCKLIST_EXACT`: 단어 전체 일치만 차단  
→ `"이라"` 추가해도 `"레스토랑이라"` 미차단 (복합어)

`_BLOCKLIST_CONTAINS`: 부분 문자열 차단  
→ 지나치게 광범위하면 정상 상호명까지 차단 위험  
→ 예: `"카페"` contains → `"카페온독"` 차단

설계 원칙: **조사·어미류는 CONTAINS, 일반명사는 EXACT**

---

## 4. 수정 이력 및 결과

### Round 0 (초기 확인, 2026-05-24)

**증상**: `sample=['온독', '바닐라브릭', '진짜']`, trends에 `'공간'(107), '대형'(103), '실내'(99)`

### Round 1 (2026-05-24, commit `4746065`)

**수정**: `'진짜'` → BLOCKLIST_EXACT, `'대형·실내·야외·공간·분위기'` → STOPWORDS  
**결과**: trends cafe에서 목표 단어 전부 제거 ✓, popular에서 `'진짜'` 제거 ✓

배치 후 trends 변화:

```text
전: ('공간',107), ('대형',103), ('실내',99), ('분위기',80), ('야외',72)
후: ('하츠',187), ('맛집',174), ('교환기',172), ('아파트',140)  ← 새 노이즈 노출
```

### Round 2 — STOPWORDS (2026-05-24, commit `7ff6bc6`)

**수정**: `'무료·교환기·아파트'` → STOPWORDS  
**결과**: 다음 배치에서 제거 예정

### Round 3 — BLOCKLIST + STOPWORDS (2026-05-24, commit `65c4568`)

**수정**:

- BLOCKLIST_EXACT: `'요즘·주소·이라·부터·와요·안성·포천'`
- BLOCKLIST_CONTAINS: `'내돈내산'`
- STOPWORDS: `'숙소·객실·빌라·여행·할인·대소변'`

**결과** (배치 후):

```text
popular/cafe:  4건 → 2건 (안성·요즘 제거, 순수 2건 유지)
popular/pension: 16건 → 12건 (내돈내산·포천·주소·이라 제거)
trends: 숙소·여행·할인·대소변 제거 ✓
```

### Round 4 — 패턴 확장 (2026-05-24, commit `e02a9a5`)

**수정**:

- 패턴 구조 `dict[str, re.Pattern]` → `dict[str, list[re.Pattern]]`
- cafe 신규 패턴: `반려동물 동반 카페 [상호명]`, `반려동물 동반 가능한 [상호명]`
- hotel 신규 패턴: `반려동물 동반 호텔 [상호명]`
- BLOCKLIST_EXACT: `'베이커리·전원주택·오션뷰·브런치'`

**결과** (배치 후):

```text
popular/cafe:   candidates 209 → 228 (증가) / count 4 → 2
                ※ count 감소는 품질 개선 (제거된 2건은 안성·요즘, 신규 추출은 임계값 미달)
popular/hotel:  count 4 → 3 ('부터' 제거 ✓)
popular/boarding: count 2 → 0 (와요·전원주택 제거 후 임계값 미달)
trends/restaurant: 여행·할인 제거 ✓, '브런치'(104) 잔존
```

---

## 5. 현재 잔존 이슈

### 5-1. Popular

| 컨텍스트 | 잔존 노이즈 | 유형 | 수정 방향 |
|---------|-----------|------|----------|
| restaurant | `'레스토랑이라'` | 복합 조사 | "이라" → BLOCKLIST_CONTAINS |
| restaurant | `'캠핑·숙소·파스타·고기집·황리단길'` | 일반명사·지명 | BLOCKLIST_EXACT |
| pension | `'횡성'` | 지명 | _LOCATION_CITY 추가 |
| pension | `'가본'` | 동사 어미 "본" | GRAMMAR_ENDING 또는 BLOCKLIST |
| boarding | count=0 | 구조적 | 쿼리 전략 재검토 |
| cafe | count=2 | recall 낮음 | 패턴 추가 또는 쿼리 확장 |

### 5-2. Trends

| 잔존 키워드 | 카테고리 | 수정 방향 |
|-----------|---------|----------|
| `'브런치'`, `'데이트'` | restaurant | STOPWORDS 추가 |
| `'식사'`, `'가족'` | restaurant·boarding | 신중 검토 (브랜드 요소 가능) |
| `'유치원'` | boarding·hotel | STOPWORDS 추가 검토 |

---

## 6. 구조적 한계 및 향후 방향

### 단기 (블록리스트 패치, 효과 체감 감소 중)

위 §5 잔존 이슈 수정. 블록리스트 라운드는 2~3회 더 가능하지만 한계점에 근접.

### 중기 (패턴·쿼리 개선, 권장)

1. **Cafe recall 개선**: 실제 제목 구조 분석 기반 패턴 추가. 현재 `반려동물 동반 가능한 [상호명]` 패턴 추가했으나 단일 언급 상호가 많아 임계값 미달. 쿼리를 특정 지역+상호 명시 형태로 변경 검토.

2. **Boarding 재설계**: 현재 쿼리(`강아지 위탁관리 후기` 등)는 창업·광고 포스트를 많이 가져옴. "특정 업체 후기" 특화 쿼리 추가 필요.

3. **MIN_MENTION_COUNT 컨텍스트별 설정**: grooming·hospital은 2 유지, cafe·hotel은 1로 낮추는 방안 (노이즈 허용 수준 판단 필요).

### 장기 (데이터 소스 확장)

- Google Places API, 카카오맵 플레이스 등 정형 업체 데이터 연동 시 recall 문제 근본 해결 가능
- 현재 아키텍처는 블로그/카페 비정형 텍스트에서 추출하는 방식으로 본질적 불확실성 존재
