# 2026-05-02 Phase 1 Refactor Log

기준 문서: `docs/superpowers/specs/2026-05-01-petory-category-recommendation-redesign.md`

## 반영 완료

1. 카테고리 리팩토링 (호환 유지)
- `supplies` 카테고리 추가
- 레거시 `snack` / `food` / `clothes` 입력은 내부적으로 `supplies`로 매핑

2. 추천 플로우 개선
- 시설 데이터가 없어도 트렌드 데이터가 있으면 LLM 추천 생성 시도
- `supplies` 요청 시 트렌드 소스를 `supplies + snack + food + clothes`로 합산

3. 수동 수집 범위 분리
- `POST /collect/trigger?scope=facilities|trends|all`
- 운영 시 트렌드만 즉시 갱신 가능

4. 트렌드 카테고리 확장
- Naver 트렌드 수집 카테고리에 `supplies` 추가

5. 문서 정합성 업데이트
- 스케줄 기준(18:00 트렌드, 18:05 시설) 통일
- API 설명에 `supplies`, `scope` 반영

## 변경 파일

- `app/recommender/facilities.py`
- `app/api/recommend.py`
- `app/recommender/builder.py`
- `app/collector/naver.py`
- `app/collector/runner.py`
- `app/api/collect.py`
- `app/schemas/recommend.py`
- `tests/test_collect_api.py` (신규)
- `tests/test_recommend_api.py`
- `tests/test_recommender.py`
- `tests/test_naver_collector.py`
- `README.md`
- `docs/USAGE.md`
- `docs/PROJECT-OVERVIEW.md`

## 테스트 결과

- 선택 실행: `23 passed`
  - `tests/test_recommend_api.py`
  - `tests/test_recommender.py`
  - `tests/test_collect_api.py`
  - `tests/test_naver_collector.py`
  - `tests/test_trends_api.py`

- 전체 실행: `47 passed, 1 failed`
  - 실패: `tests/test_geocoder.py::test_geocode_success`
  - 원인: 현재 지오코더 구현은 Kakao 기준인데 테스트는 구형 Naver Map 목(mock) 기준

## 남은 작업 (권장)

1. `supplies` 전용 시설 소스 확장
- 현재는 `BUSINESS`를 재활용하므로 용품점 정확도 제한

2. 지오코더 테스트 정합성 수정
- Kakao 구현 기준으로 테스트 케이스 갱신 필요

3. 추천 응답 스키마 고도화
- 후보별 점수(`score_breakdown`) 노출은 다음 단계
