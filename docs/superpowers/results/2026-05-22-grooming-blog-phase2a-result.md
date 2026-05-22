# Phase 2a 구현 결과 — grooming_blog 상호명 추출 품질 개선

**구현일:** 2026-05-22  
**대상 파일:** `app/ingestion/grooming_blog.py`, `tests/test_grooming_blog.py`  
**스펙:** `docs/superpowers/specs/2026-05-22-grooming-blog-extraction-quality-design.md`

---

## 무엇이 달라졌나

`extract_context_mentions`가 반환하는 `mention_map`의 키가 **텍스트 파편 → 실제 업장명**으로 정제됨.

### 변경 전 문제

| 입력 텍스트 | 변경 전 추출값 | 문제 |
|---|---|---|
| `두유네 애견미용실 후기` | `"두유네 애견"` | 공백 포함 파편 |
| `#반려동물 #애견미용` | `"#반려동물 #"` | 특수문자 포함 파편 |
| `강서구 1인 미용실` | `"강서구 1인"` | 지명+숫자 파편 |
| `맘바이강아지미용실` | blocklist 오차단 | "강아지" 포함→exact 비교 불가 |
| `애견 셀프목욕 후기` | `"셀프목욕"` | prefix false positive |
| `니니 애견 미용실` | (없음) | 공백 구분 구조 미포착 |

### 변경 후 결과

| 입력 텍스트 | 추출값 | 처리 경로 |
|---|---|---|
| `두유네 애견미용실 후기` | `"두유네"` ✓ | suffix 패턴 |
| `니니 애견 미용실 예약` | `"니니"` ✓ | suffix bridge token |
| `맘바이강아지미용실 예약` | `"맘바이강아지"` ✓ | BLOCKLIST_EXACT (exact만 차단) |
| `#반려동물 #애견미용` | (없음) ✓ | 문자 클래스 차단 |
| `강서구 1인 미용실` | (없음) ✓ | location filter + 한글 1자 탈락 |
| `반려동물 동반 안산 추천 미용실` | (없음) ✓ | BLOCKLIST_CONTAINS "추천" |
| `화원강아지미용실 다녀왔어요` | `"화원강아지"` ✓ | suffix 패턴 |
| `애견 셀프목욕 방문 후기` | (없음) ✓ | PREFIX suffix 앵커 |
| `ABC미용 그루밍샵 예약했어요` | `"ABC미용"` ✓ | 혼합형 (한글 2자 연속 포함) |
| `예약제미용실 체험기` | (없음) ✓ | BLOCKLIST_EXACT "예약제" |

---

## 코드 변경 내역

### 1. 캡처 문자 클래스 고정 (전 컨텍스트)

`.{2,N}` → `[가-힣a-zA-Z0-9]{2,N}`

공백·`#`·`@`·특수문자가 캡처 그룹에 들어오지 못하게 원천 차단.

### 2. grooming suffix 패턴 — bridge token 추가

```python
# 변경 전
re.compile(r"(.{2,10})\s*(?:미용실|애견미용|펫미용|그루밍샵)")

# 변경 후
re.compile(
    r"([가-힣a-zA-Z0-9]{2,10})"
    r"(?:\s+(?:애견|반려견|펫))?"
    r"\s*(?:미용실|애견미용|펫미용|그루밍샵)"
)
```

"니니 애견 미용실" 같은 **업장명 + 수식어 + 카테고리** 구조 포착.

### 3. grooming prefix 패턴 — suffix 앵커 추가

```python
# 변경 전
re.compile(r"(?:애견|반려견|펫)\s*(.{2,8})")

# 변경 후
re.compile(r"(?:애견|반려견|펫)\s*([가-힣a-zA-Z0-9]{2,8})\s*(?:미용실|애견미용|펫미용|그루밍샵)")
```

"애견 셀프목욕", "펫 드라이룸" 같은 **일반 명사 false positive 원천 차단**.

### 4. _CANDIDATE_SANITIZE — `#@` 추가

### 5. 블록리스트 이중화

```python
# 변경 전: 단일 frozenset (_BLOCKLIST) — exact 비교만
_BLOCKLIST = frozenset(["강아지", "미용실", ...])

# 변경 후
_BLOCKLIST_EXACT = frozenset([...])     # exact 일치만 차단
_BLOCKLIST_CONTAINS = frozenset([...]) # 포함되면 차단 (추천, 후기, 협찬 등)
```

"맘바이강아지"처럼 블록리스트 단어를 포함하는 실제 업장명의 오차단 해소.

### 6. `_is_location_fragment` 신규 추가

```python
_LOCATION_SUFFIX = re.compile(r'[가-힣]{1,5}(?:구|시|군|동|읍|면|로|역)$')
```

"강서구", "봉화산로", "홍대역" 차단. "길"·"가"는 업장명 충돌 위험으로 제외.

### 7. `_is_valid_name` 신규 추가 — 4단계 필터 체인

```
BLOCKLIST_EXACT → BLOCKLIST_CONTAINS → location → 한글 2자 연속
```

---

## 테스트 결과

```
20 passed in 0.09s
```

| 구분 | 케이스 수 |
|---|---|
| 기존 테스트 (회귀 없음) | 10 |
| 신규 스펙 케이스 | 10 |
| 합계 | **20 / 20 통과** |

---

## 영향 범위

- `grooming_blog.py` 단독 수정 (인프라 변경은 전 컨텍스트 적용)
- `naver.py`, `runner.py`, Redis 스키마 **무변경**
- `mention_map` 반환 타입 `dict[str, dict]` **불변**

---

## 남은 한계 (Phase 2b 과제)

| 케이스 | 현황 |
|---|---|
| `예약제미용실` | BLOCKLIST_EXACT "예약제" 추가로 현재 차단됨 — 관측 기반 확장 필요 |
| `프리미엄미용실`, `일인미용실` 등 서술어+suffix | suffix 패턴 구조상 차단 불가 — 관측 후 BLOCKLIST_EXACT 추가 대응 |
| `멍미용 강남점` 등 점명 패턴 | 현재 패턴 미매칭 — 별도 패턴 필요 |
| hospital/cafe/supplies prefix suffix 앵커 | grooming 전용 적용; 타 컨텍스트는 각 담당자가 정의 |
| 순수 영문 상호명 (ABC, K9) | 한글 2자 연속 필터로 설계상 미지원 |
