# Step 2: 테스트 작성 (test_facilities_api.py)

## 목표

`GET /facilities` 엔드포인트의 핵심 케이스를 pytest로 검증한다.

## 변경 파일

### `tests/test_facilities_api.py` (신규)

기존 `tests/test_popular_api.py` 패턴을 따른다.

테스트 케이스:
1. Redis에 address 있는 popular 데이터 → 정상 반환
2. address 없는 항목 자동 제외
3. cursor 페이징 동작
4. Redis 비어있을 때 빈 배열 반환 (503 아님)
5. 인증 없으면 403

## AC

```bash
cd /Users/maknkkong/project/pet-data-api && source venv/bin/activate
pytest tests/test_facilities_api.py -v
pytest tests/ -v   # 기존 테스트 회귀 없음
```
