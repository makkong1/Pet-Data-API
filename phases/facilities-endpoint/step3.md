# Step 3: 커밋 + 푸시 + MD 문서 업데이트

## 목표

구현 완료 후 커밋·푸시하고 docs 업데이트한다.

## 작업

### 커밋
```bash
git add app/serving/api/facilities.py app/main.py tests/test_facilities_api.py
git commit -m "feat(facilities): GET /facilities cursor-based endpoint for Petory sync"
git push origin dev
```

### MD 업데이트

`docs/분析/04-petory-nearby-signal-architecture-redesign.md` §8 요약 테이블:
- `GET /facilities` 항목을 `❌ 빠진 것` → `✅ 구현됨` 으로 변경

`docs/분析/05-petory-backend-changes.md` §5 체크리스트:
- `□ pet-data-api GET /facilities 구현 완료 확인` → `☑` 체크

## AC

```bash
git log --oneline -3
curl -s -H "X-API-Key: $API_KEY" http://localhost:8000/facilities | python3 -c "import sys,json; d=json.load(sys.stdin); print('items:', len(d['items']), 'has_next:', d['has_next'])"
```
