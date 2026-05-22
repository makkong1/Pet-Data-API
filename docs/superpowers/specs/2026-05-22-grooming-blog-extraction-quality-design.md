# 네이버 블로그 상호명 추출 품질 개선 (Phase 2a) 설계 문서

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**작성일:** 2026-05-22  
**대상 파일:** `app/ingestion/grooming_blog.py`  
**배경:** Phase 1 이후 P3 재관찰 — `_SUFFIX_PATTERNS`의 `.{2,10}` 이 공백 포함 문장 파편을 캡처, `_BLOCKLIST` exact 비교가 "맘바이강아지" 같은 실제 상호명을 오차단. mention 신호가 실제 공공 DB 시설과 매핑되지 않는 문제.

---

## 목표

`extract_context_mentions`가 반환하는 `mention_map` 키가 **실제 업장명**("두유네", "니니", "맘바이강아지")이 되도록.  
텍스트 파편("강서구 1인", "#반려동물 #", "려동물 동반 가능한")은 추출 단계에서 차단.  
`naver.py`, `runner.py`, Redis 스키마 무변경.

---

## 변경 범위

`app/ingestion/grooming_blog.py` 한 파일만 수정.  
테스트: `tests/test_grooming_blog.py` (기존 스타일 유지, 케이스 보강).

---

## 설계

### 1. 패턴 재설계

#### 1-1. 문자 클래스 고정 (`[가-힣a-zA-Z0-9]`)

모든 패턴의 캡처 그룹 `.{2,10}` → `[가-힣a-zA-Z0-9]{2,10}` 으로 교체.  
공백·`#`·`@`·특수문자를 캡처 불가로 만들어 파편 원천 차단.

#### 1-2. SUFFIX 확장 — 공백 케이스 포착

"니니 애견 미용실", "두유네 애견미용실" 처럼 업장명과 카테고리 접미어 사이에 공백이 있는 경우를 추가 포착.

```python
# 변경 전 (grooming 예시)
re.compile(r"(.{2,10})\s*(?:미용실|애견미용|펫미용|그루밍샵)")

# 변경 후
re.compile(
    r"([가-힣a-zA-Z0-9]{2,10})"
    r"(?:\s+(?:애견|반려견|펫))?"     # "니니 애견 미용실" 케이스
    r"\s*(?:미용실|애견미용|펫미용|그루밍샵)"
)
```

`(?:\s+(?:애견|반려견|펫))?` 가 있으면 "두유네 애견미용실" → "두유네", "니니 애견 미용실" → "니니" 모두 포착.

#### 1-3. PREFIX 패턴 — suffix 앵커 추가 (문자 클래스만으로는 false positive 차단 불가)

**문제**: 문자 클래스만 교체하면 "애견 셀프목욕", "펫 드라이룸", "애견 호텔 추천" 같은 일반 명사가 `_is_valid_name`을 통과한다. 해당 단어들은 한글 2자 이상·blocklist 미해당이기 때문.  
**해결**: 동일 구 안에 suffix가 있어야만 유효 후보로 처리.

```python
# 변경 전
re.compile(r"(?:애견|반려견|펫)\s*(.{2,8})")

# 변경 후 — suffix 앵커 추가 (단독 명사 false positive 원천 차단)
re.compile(r"(?:애견|반려견|펫)\s*([가-힣a-zA-Z0-9]{2,8})\s*(?:미용실|애견미용|펫미용|그루밍샵)")
```

"애견 두유네 미용실" → "두유네" ✓, "애견 셀프목욕" → (없음) ✓.  
"니니 애견 미용실"처럼 업장명이 prefix 앞에 위치하는 케이스는 1-2의 suffix 패턴(bridge token)이 담당.

#### 1-4. `_CANDIDATE_SANITIZE` — `#` 추가

```python
# 변경 전
_CANDIDATE_SANITIZE = re.compile(r'[\"\'""''·\[\]\(\)\{\}]')

# 변경 후
_CANDIDATE_SANITIZE = re.compile(r'[\"\'""''·\[\]\(\)\{\}#@]')
```

---

### 2. 블록리스트 두 버킷

#### 2-1. `_BLOCKLIST_EXACT` (단독 이름이면 차단, 상호명 포함은 허용)

"맘바이강아지"처럼 상호명 안에 포함될 수 있는 단어는 exact 비교만.

```python
_BLOCKLIST_EXACT = frozenset([
    "강아지", "고양이", "반려동물", "반려견", "애견", "펫", "동물",
    "미용실", "미용", "샵", "살롱", "병원", "용품", "용품점",
    "사료", "간식", "진료", "24시",
])
```

#### 2-2. `_BLOCKLIST_CONTAINS` (포함되면 차단 — 스팸·서술어만)

"추천", "후기" 같이 업장명에 포함될 수 없는 서술어/스팸 지시어만. 지명·일반 형용사는 제외 → 별도 `_is_location_fragment`가 담당.

```python
_BLOCKLIST_CONTAINS = frozenset([
    "추천", "후기", "근처", "인근", "주변", "동네",
    "자격증", "학원", "협찬", "원고료", "광고",
])
```

---

### 3. 행정구역·도로명 방어선 (`_is_location_fragment`)

`_BLOCKLIST_CONTAINS` 에 지명을 넣지 않고 별도 규칙으로 분리.  
명확한 행정/도로 접미어(구·시·군·동·읍·면·로·역)만 대상. `가`·`길`은 상호명과 충돌 위험으로 제외.

```python
_LOCATION_SUFFIX = re.compile(r'[가-힣]{1,5}(?:구|시|군|동|읍|면|로|역)$')

def _is_location_fragment(name: str) -> bool:
    return bool(_LOCATION_SUFFIX.search(name))
```

| 이름 | 판정 | 이유 |
|------|------|------|
| `강서구` | ✗ 차단 | "구" suffix |
| `봉화산로` | ✗ 차단 | "로" suffix |
| `홍대역` | ✗ 차단 | "역" suffix |
| `두유네` | ✓ 통과 | 해당 없음 |
| `맘바이강아지` | ✓ 통과 | 해당 없음 |
| `행복길` | ✓ 통과 | "길" 제외로 오차단 없음 |

---

### 4. 최종 유효성 필터 (`_is_valid_name`)

기존 `if len(name) >= 2 and name not in _BLOCKLIST:` 를 아래로 교체.

```python
def _is_valid_name(name: str) -> bool:
    if name in _BLOCKLIST_EXACT:
        return False
    if any(b in name for b in _BLOCKLIST_CONTAINS):
        return False
    if _is_location_fragment(name):
        return False
    if not re.search(r'[가-힣]{2,}', name):   # 한글 2자 연속 필수
        return False
    return True
```

**캡처 패턴(`[가-힣a-zA-Z0-9]`)과 이 필터의 관계:**

| 후보 | 한글 2자 연속 | 결과 |
|------|-------------|------|
| `ABC미용` | "미용" ✓ | 통과 |
| `K9펫미용` | "펫미용" ✓ | 통과 |
| `ABC` | 없음 | 탈락 |
| `1인` | "인" 1자 | 탈락 |
| `M2` | 없음 | 탈락 |

순수 영문/숫자 상호명은 설계 범위 외. `a-zA-Z0-9`를 캡처 클래스에 포함한 이유는 혼합형(ABC미용, K9펫미용)을 포착하기 위함.

`_extract_candidates_from_text` 내부의 필터 호출을 `_is_valid_name(name)` 으로 통일.

---

## 변경 전/후 비교 (grooming 기준)

| 입력 | 변경 전 | 변경 후 | 차단 경로 |
|------|---------|---------|---------|
| `두유네 애견미용실` | "두유네 애견" (파편) | "두유네" ✓ | suffix 패턴(bridge) |
| `니니 애견 미용실` | (없음) | "니니" ✓ | suffix 패턴(bridge) |
| `맘바이강아지미용실` | "맘바이강아지" (단 오차단 위험) | "맘바이강아지" ✓ | — |
| `#반려동물 #애견미용` | "#반려동물 #" (파편) | (없음) ✓ | 문자 클래스(# 제외) |
| `강서구 1인 미용실` | "강서구 1인" (파편) | (없음) ✓ | "1인" → 한글 1자 탈락; "강서구" → location filter |
| `반려동물 동반 안산 화원강아지미용실` | "반 안산 화원강아지" | "화원강아지" ✓ | — |
| `애견 셀프목욕 후기` | "셀프목욕" (false positive) | (없음) ✓ | PREFIX suffix 앵커 (1-3 변경) |
| `ABC미용 그루밍샵 다녀왔어요` | (없음) | "ABC미용" ✓ | 한글 2자 연속 "미용" 포함 |
| `예약제미용실 후기` | "예약제" (false positive) | "예약제" ⚠ | **현재 차단 불가** — 한글 3자 통과. `_BLOCKLIST_EXACT`에 "예약제"·"일인"·"프리미엄" 등 관측 추가로 대응 (Phase 2b) |
| `멍미용 강남점 가격` | (없음) | (없음) — 별도 패턴 필요 시 Phase 2b | — |

---

## 테스트 전략

기존 `tests/test_grooming_blog.py` 스타일 유지. 아래 케이스 추가:

| # | 입력 | 기대 출력 | 분류 |
|---|------|----------|------|
| 1 | `두유네 애견미용실 후기` | `{"두유네"}` | ✅ 정상 |
| 2 | `맘바이강아지미용실 예약` | `{"맘바이강아지"}` | ✅ 정상 |
| 3 | `니니 애견 미용실 예약` | `{"니니"}` | ✅ 정상 |
| 4 | `#반려동물 #애견미용 #헤어스파` | `set()` | ❌ 차단 (문자 클래스) |
| 5 | `강서구 1인 미용실 후기` | `set()` | ❌ 차단 (location·한글 1자) |
| 6 | `반려동물 동반 안산 추천 미용실` | `set()` | ❌ 차단 (BLOCKLIST_CONTAINS "추천") |
| 7 | `화원강아지미용실 다녀왔어요` | `{"화원강아지"}` | ✅ 정상 |
| 8 | `애견 셀프목욕 방문 후기` | `set()` | ❌ 차단 (PREFIX suffix 앵커) |
| 9 | `ABC미용실 예약했어요` | `{"ABC미용"}` | ✅ 정상 (혼합형) |
| 10 | `예약제미용실 체험기` | `set()` | ⚠ known limitation — 통과함. `_BLOCKLIST_EXACT`에 "예약제" 추가 후 재검증 |

---

## 영향 범위

- `grooming_blog.py` 내 `_SUFFIX_PATTERNS`, `_PREFIX_PATTERNS`, `_BLOCKLIST`, `_CANDIDATE_SANITIZE`, `_extract_candidates_from_text` 함수
- **인프라 변경 — 전 컨텍스트 일괄 적용**: 문자 클래스(`[가-힣a-zA-Z0-9]`), 블록리스트 이중 구조(`_BLOCKLIST_EXACT`/`_BLOCKLIST_CONTAINS`), `_is_valid_name` 교체, `_is_location_fragment` 추가
- **suffix·prefix 토큰 목록 — 컨텍스트별 별도 유지**: 본 문서는 grooming 전용(미용실·애견미용·그루밍샵 등). hospital(`동물병원`·`동물 병원`), cafe(`애견카페`·`애견 카페`), supplies 등의 공백 변형 규칙은 동일 패턴 구조를 따르되 각 컨텍스트 담당자가 토큰 정의 — 본 문서 범위 외
- 하위 호환: `mention_map` 반환 타입 `dict[str, dict]` 불변, `runner.py` / Redis 무변경
