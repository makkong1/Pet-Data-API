# LocationImportService Source-Aware Upsert 설계

**날짜:** 2026-05-26  
**대상 레포:** Petory  
**배경:** 현재 `LocationImportService.processEntries()`는 `name+address` 중복 시 skip한다. 매일 파일을 교체해도 DB는 첫 적재 이후 사실상 갱신되지 않아 전화번호·좌표·카테고리 변경이 반영되지 않는다. 폐업된 시설도 DB에 계속 남는다.

---

## 목표

`BATCH_IMPORT` 소유 row에 한해, 동일 시설이 다시 들어오면 **갱신**, 처음이면 **삽입**, 예전에 soft-delete됐다면 **재활성화**한다. 다른 출처(PUBLIC, 수기 등)는 건드리지 않는다.

---

## 변경 파일

| 파일 | 변경 |
|------|------|
| `LocationServiceRepository` | 시그니처 추가 |
| `SpringDataJpaLocationServiceRepository` | JPA 메서드 추가 |
| `JpaLocationServiceAdapter` | 위임 구현 추가 |
| `LocationImportService` | upsert 로직 교체, SyncResult 변경 |
| `LocationImportServiceTest` (신규 or 기존) | upsert·재활성화·insert 케이스 |

DB 마이그레이션 없음. 기존 `lastUpdated` (LocalDate) 재활용.

---

## 새 Repository 메서드

```java
// isDeleted 무관하게 찾아야 함 — soft-deleted row도 포함
Optional<LocationService> findByNameAndAddressAndDataSource(
    String name, String address, String dataSource);
```

**이유:** soft-deleted row를 못 찾으면, 같은 시설이 다시 파일에 들어올 때 중복 insert가 생긴다.

---

## processEntries() 로직

```
for each dto in dtos:
  if !isValid(dto):
    skipped++
    continue

  existing = repo.findByNameAndAddressAndDataSource(dto.name, dto.address, "BATCH_IMPORT")

  if existing.isPresent():
    // 항상 갱신
    existing.phone      = dto.phone
    existing.latitude   = dto.lat
    existing.longitude  = dto.lng
    existing.sido       = dto.sido
    existing.sigungu    = dto.sigungu
    existing.category3  = categoryLabel(dto.category)
    existing.lastUpdated = LocalDate.now()

    // soft-deleted였다면 복구
    if existing.isDeleted == true:
      existing.isDeleted  = false
      existing.deletedAt  = null

    repo.save(existing)
    updated++

  else:
    entity = toEntity(dto)          // lastUpdated=today 포함
    batch.add(entity)
    if batch.size >= batchSize:
      saved += batchWriter.saveBatch(batch)
      batch.clear()

if !batch.isEmpty():
  saved += batchWriter.saveBatch(batch)
```

**보존 필드 (갱신 금지):** `rating`, `reviewCount`, `score`, `dataSource`, `isDeleted`(복구 경로 제외)

---

## toEntity() 변경

기존 `toEntity(dto)`에 `lastUpdated = LocalDate.now()` 추가. insert 시점도 touch 기록이 필요하기 때문.

---

## SyncResult

```java
// 변경 전
SyncResult(total, saved, duplicate, skipped)

// 변경 후
SyncResult(total, saved, updated, skipped)
```

`duplicate` 제거. 이제 중복은 update로 처리되므로 duplicate 개념이 사라진다.

로그: `[LocationImportService] 완료 total={} saved={} updated={} skipped={}`

---

## isValid() 동작

변경 없음. `status == "폐업"` skip은 현재 exporter가 항상 "운영중"을 쓰므로 사실상 dead code지만, 확장 여지를 위해 유지한다.

---

## lastUpdated 활용 방향 (C 방향)

- `BATCH_IMPORT` row의 `lastUpdated`가 마지막 sync에서 touch된 날짜를 의미한다.
- 미래에 `lastUpdated < 기준일`인 row를 "누락 항목 후보"로 탐지하는 운영 쿼리 또는 스케줄러를 붙일 수 있다.
- 이번 구현에서는 missing items 자동 soft-delete 없음. 정책은 추후 결정.

---

## 테스트 케이스

| 케이스 | 결과 |
|--------|------|
| 새 BATCH_IMPORT row | saved++ |
| 기존 BATCH_IMPORT row (active) | updated++, 갱신 필드 반영 |
| 기존 BATCH_IMPORT row (soft-deleted) | updated++, isDeleted=false 복구 |
| 기존 PUBLIC row (같은 name+address) | 건드리지 않음 (saved or updated 없음) |
| isValid 실패 (lat/lng null 등) | skipped++ |
| rating·reviewCount 보존 확인 | 갱신 후 동일값 유지 |

---

## 범위 외

- C (아키텍처 명확화), B (supplies Track A 편입) — 별도 스펙
- PetDataApiClient dead code 정리 — 별도 작업
- 카테고리 매핑 중복 제거 — 별도 작업
