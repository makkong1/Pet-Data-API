# Phase 2a 검토 결과 — grooming_blog 상호명 추출 품질 개선

**검토일:** 2026-05-22  
**대상 파일:** `app/ingestion/grooming_blog.py`, `tests/test_grooming_blog.py`  
**관련 스펙:** `docs/superpowers/specs/2026-05-22-grooming-blog-extraction-quality-design.md`

**관련 근거 문서**

| 경로 | 용도 |
|------|------|
| `docs/troubleshooting/2026-05-21-naver-phase1-and-recommend-log.md` | Phase 1 이후 P3 재관찰, mention 노이즈·파편 사례 |
| `docs/분석/README.md` | 분석 폴더 인덱스(아래 목록 진입점) |
| `docs/분석/01-프로젝트-전체-이해-가이드.md` | 서빙/수집 경로를 읽을 때의 큰 지도 |
| `docs/분석/03-naver-blog-trend-ingestion.md` | 네이버 블로그 **트렌드 수집(naver/analyzer/runner)** 쪽 페이즈·RawItem 제안과의 정렬 참고 (**Phase 2a와 책임이 다름**) |

---

## 검토 범위

이번 문서는 "구현 완료 보고"보다는 아래를 대조한 **검토 결과**다.

1. Phase 2a 스펙에 적힌 설계 의도  
2. 현재 `grooming_blog.py` 실제 구현 상태  
3. `tests/test_grooming_blog.py` 규격 케이스와 (가능하면) 실행 결과  

`docs/analysis/` 같은 **영문 경로 디렉터리는 레포에 없다.** 대신 동일 목적 모음은 **`docs/분석/`** 에 있으며(`README.md`·번호 매긴 분석 노트), 검토 시 혼동하지 않도록 본 결과 문서에서는 그 경로를 기준으로 쓴다.

---

## 결론

현재 구현은 **grooming 컨텍스트 한정 hotfix로는 수용 가능**하다.

- 공백 포함 파편 추출 문제는 문자 클래스 고정으로 줄였다.
- `"니니 애견 미용실"` 같은 공백 변형은 grooming suffix bridge(`(?:\\s+(?:애견|반려견|펫))?`)로 회수한다.
- `"애견 셀프목욕"` 같은 prefix false positive는 grooming prefix에 suffix 앵커를 붙여 차단했다.
- `"맘바이강아지"` 같은 실제 상호명은 `_BLOCKLIST_EXACT` / `_BLOCKLIST_CONTAINS` 분리로 살렸다.
- 지명 파편은 `_LOCATION_SUFFIX` + `_is_location_fragment()`로 1차 방어한다(`가`/`길` 제외 및 `$` 접미 규칙은 스펙과 동일).

다만 이 변경은 **범용 추출기 개선**이 아니라 **grooming 전용 정규식·앵커 보정**에 가깝다. hospital/cafe/supplies 등 다른 컨텍스트에는 **문자 클래스만** 공통 적용되었고, grooming과 동일한 prefix suffix 앵커 강화가 들어간 것은 아니다.

---

## 확인된 구현 상태

### 1. 기존 리뷰 포인트 반영 여부

| 항목 | 검토 의견 | 현재 상태 |
|---|---|---|
| prefix false positive | `(?:애견|펫)\\s*이름`만으로는 일반 명사 누수 위험 | **반영됨** — grooming prefix에 suffix 앵커 추가 |
| suffix 파편 추출 | `.{2,10}`이 공백/문장 파편을 흡수 | **반영됨** — 전 컨텍스트 suffix 캡처를 `[가-힣a-zA-Z0-9]{2,N}`로 축소 |
| exact/contains 분리 | `"맘바이강아지"` 오차단 위험 | **반영됨** — `_BLOCKLIST_EXACT`, `_BLOCKLIST_CONTAINS` 분리 |
| 전 컨텍스트 과도 일반화 | grooming 규칙을 전체에 동일 적용하는 서술은 위험 | **코드상** — suffix bridge·prefix 앵커는 **grooming만**; 나머지는 문자 클래스 수준 |
| 영문/혼합 상호명 계약 모호성 | 허용 문자와 최종 필터가 충돌 가능 | **명시됨** — `_HANGUL_MIN2`(한글 연속 2자 이상) 유지. 영문 전용 상호는 의도적으로 제외 |
| 서술어형 접미 | `예약제미용실` 등 | **보강됨** — `_BLOCKLIST_EXACT`에 `"예약제"` 추가(스펙 케이스 10·테스트로 고정) |

### 2. 현재 코드상 핵심 방어선

`app/ingestion/grooming_blog.py` 기준.

- **grooming suffix**  
  `([가-힣a-zA-Z0-9]{2,10})(?:\\s+(?:애견|반려견|펫))?\\s*(?:미용실|애견미용|펫미용|그루밍샵)`
- **grooming prefix**  
  `(?:애견|반려견|펫)\\s*([가-힣a-zA-Z0-9]{2,8})\\s*(?:미용실|애견미용|펫미용|그루밍샵)`
- **non-grooming**: suffix/prefix는 위와 달리 **앵커·bridge 없이** 기존 구조 + 문자 클래스만 적용
- **후보 필터**: `_BLOCKLIST_EXACT`, `_BLOCKLIST_CONTAINS`, `_is_location_fragment`, `_HANGUL_MIN2`
- **sanitize**: `_CANDIDATE_SANITIZE`에 `#`, `@` 포함(유니코드 이스케이프 형태의 한 줄 패턴)

즉, Phase 2a는 단순 blocklist 추가가 아니라 **정규식 단계 + 후처리 단계**를 같이 손본 구조다.

---

## 검증 결과

`Settings`가 import 시점에 필수 환경변수를 요구하므로, 로컬에서는 **`.env` 로드** 또는 아래처럼 최소 변수를 export한 뒤 실행한다.

```bash
cd pet-data-api
# .env 가 있으면 자동 로드되는 환경에서 실행하거나, 없으면 필수 키만 채운 뒤:
./venv/bin/pytest tests/test_grooming_blog.py -q
```

샌드박스·CI에서 더미 값으로 돌린 최근 실행 예:

```text
20 passed in 0.09s
```

포함된 검증 포인트(스펙 케이스 및 회귀):

| 입력 요지 | 기대 |
|-----------|------|
| `두유네 애견미용실 후기` | `두유네` |
| `맘바이강아지미용실 예약` | `맘바이강아지` |
| `니니 애견 미용실 예약` | `니니` |
| `#반려동물 #애견미용 #헤어스파` | ∅ |
| `강서구 1인 미용실 후기` | ∅ |
| `반려동물 동반 안산 추천 미용실` | ∅ (contains `추천`) |
| `화원강아지미용실 다녀왔어요` | `화원강아지` |
| `애견 셀프목욕 방문 후기` | ∅ (prefix·suffix 미정렬) |
| `ABC미용 그루밍샵 예약했어요` | `ABC미용`(한글 2자 이상 포함 혼합) |
| `예약제미용실 체험기` | ∅ (`예약제` exact) |

`tests/test_grooming_blog.py`는 현재 **20개** 테스트(비동기 3 + 스펙 10 + 기존 7)로 위를 커버한다.

---

## `docs/분석`과의 역할 분리

- **`docs/분석/03-naver-blog-trend-ingestion.md`** 는 `naver.py` ↔ 형태소 ↔ Redis 트렌드 쪽의 **dual-sort·dedupe·향후 RawItem·quality_score** 를 다룬다.
- 본 Phase 2a는 **`grooming_blog.py` 멘션 추출**로, 같은 “블로그 텍스트”를 쓰더라도 **추천 파이프의 Kakao 후보 생성** 목적과 데이터 플로가 다르다.  
문서 간 교차 참조만 할 때 이 경계를 유지하면 면접·온보딩 설명이 섞이지 않는다.

---

## 남은 리스크

### 1. non-grooming 컨텍스트는 아직 느슨하다

문자 클래스 축소는 전 컨텍스트에 들어갔지만, grooming처럼 prefix에 suffix 앵커를 넣거나 optional bridge를 둔 강화는 다른 컨텍스트에는 동일하게 적용되지 않았다. hospital/cafe/supplies 쪽에는 비슷한 false positive가 남아 있을 수 있다.

### 2. 서술어+suffix 차단은 아직 규칙 확장형이다

`예약제`는 exact blocklist로 막았다. `프리미엄미용실`, `일인미용실`, `소형견미용실` 같은 표현은 관측에 따라 다시 샐 수 있다.

### 3. 순수 영문 상호명은 설계상 미지원이다

문자 클래스는 영문/숫자를 허용하지만 최종 필터가 한글 2자 연속을 요구한다. `ABC`, `K9` 같은 이름은 의도적으로 버리는 계약이다.

### 4. 기존 기본 테스트 중 일부는 여전히 약하다

`test_extract_candidates_prefix_pattern()`의 `assert len(result) >= 0`는 사실상 무의미하다. 스펙 케이스가 실질 검증을 대신하고 있지만, 회귀 테스트도 더 명시적으로 바꾸는 편이 낫다.

---

## 최종 판단

Phase 2a는 **“grooming mention 추출 품질을 급한 수준으로 바로잡는 패치”**로 보면 타당하다.  
반면 **범용 상호명 추출기 완성**으로 해석하면 아직 아니다.

권장 해석:

- **승인 가능 범위**: grooming 추천 파이프의 mention 신호 품질 개선  
- **보류해야 할 주장**: 모든 컨텍스트에서 실제 업장명 추출이 동일하게 안정화됐다  
- **다음 우선순위**: non-grooming 회귀 케이스 수집; `docs/분석/03` 과 맞물리는 naver 트렌드 Phase 2b(의도별 RawItem 등)와 **책임 분리 유지**
