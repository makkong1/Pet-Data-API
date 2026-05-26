# Local Batch Pipeline Connection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Python CLI 출력 JSON 파일과 Spring FacilitySyncScheduler를 공유 경로로 연결해 로컬에서 데이터가 실제로 흐르게 한다.

**Architecture:** `~/data/pet-locations.json` 을 공유 경로로 사용. Python CLI가 이 경로에 쓰고, Spring `FacilitySyncScheduler`(매일 01:00)가 이 경로에서 읽는다. 변경 사항은 Spring properties 1줄 + CLAUDE.md 문서화가 전부.

**Tech Stack:** Python 3.11+ (cli.py), Spring Boot 3 (application-dev.properties)

---

## 코드베이스 핵심 사실

```
# Petory
backend/main/resources/application-dev.properties:12
  → app.location.import.file-path=   ← 여기에 경로 설정

# pet-data-api
cli.py  → python cli.py popular --output <path>

CLAUDE.md:91  → ## 실행 섹션에 배치 CLI 명령 추가
```

Spring `FacilitySyncScheduler` 동작:

- `app.location.import.file-path` 가 비어있으면 → INFO 로그 후 스킵
- 값이 있으면 → `LocationImportService.importFromFile(path)` 호출 → validate + dedup + DB upsert

---

## 파일 맵

| 작업 | 파일                                                       |
| ---- | ---------------------------------------------------------- |
| 수정 | `Petory/backend/main/resources/application-dev.properties` |
| 수정 | `pet-data-api/CLAUDE.md`                                   |

---

## Task 1: 공유 디렉토리 생성

- [ ] **Step 1: ~/data 디렉토리 생성**

```bash
mkdir -p ~/data
```

Expected: 오류 없이 완료 (이미 존재해도 무시)

---

## Task 2: Spring 파일 경로 설정

**Files:**

- Modify: `Petory/backend/main/resources/application-dev.properties:12`

- [ ] **Step 1: file-path 값 설정**

`app.location.import.file-path=` 줄을 아래로 교체:

```properties
app.location.import.file-path=/Users/maknkkong/data/pet-locations.json
```

- [ ] **Step 2: 컴파일 확인**

```bash
cd /Users/maknkkong/project/Petory
./gradlew compileJava -x test
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 3: 커밋**

```bash
cd /Users/maknkkong/project/Petory
git add backend/main/resources/application-dev.properties
git commit -m "chore(location): file-path 설정 — Python batch 출력 경로 연결"
```

---

## Task 3: CLAUDE.md 배치 CLI 실행 명령 추가

**Files:**

- Modify: `pet-data-api/CLAUDE.md` (## 실행 섹션)

- [ ] **Step 1: 배치 CLI 항목 추가**

`## 실행` 섹션의 기존 코드블록 바로 뒤에 아래 내용 추가:

````markdown
### 배치 CLI (Petory DB 적재용)

```bash
# ~/data 디렉토리 없으면 먼저 생성
mkdir -p ~/data

# 전체 컨텍스트 수집 → ~/data/pet-locations.json 출력
source venv/bin/activate
PYTHONPATH=. python cli.py popular --output ~/data/pet-locations.json

# 특정 컨텍스트만 (검증용)
PYTHONPATH=. python cli.py popular --output ~/data/pet-locations.json --contexts grooming hospital
```
````

출력 파일은 Spring `FacilitySyncScheduler`(매일 01:00)가 자동으로 읽어 Petory DB에 적재한다.

````

- [ ] **Step 2: 커밋**

```bash
cd /Users/maknkkong/project/pet-data-api
git add CLAUDE.md
git commit -m "docs: 배치 CLI 실행 명령 추가 — ~/data/pet-locations.json 공유 경로 연결"
````

---

## Task 4: 엔드투엔드 검증

- [ ] **Step 1: 소규모 컨텍스트로 CLI 실행**

```bash
cd /Users/maknkkong/project/pet-data-api
source venv/bin/activate
PYTHONPATH=. python cli.py popular --output ~/data/pet-locations.json --contexts grooming
```

Expected: `[cli] popular: N건 → /Users/maknkkong/data/pet-locations.json`

- [ ] **Step 2: JSON 파일 내용 확인**

```bash
python -m json.tool ~/data/pet-locations.json | head -30
```

Expected: `name`, `category`, `lat`, `lng` 등 필드 포함된 JSON 배열

- [ ] **Step 3: Spring importFromFile 직접 호출로 파일 읽기 확인**

Spring 서버 실행 상태에서:

```bash
curl -s -X POST http://localhost:8080/api/admin/location/import \
  -H "Authorization: Bearer <ADMIN_JWT>" \
  -F "file=@/Users/maknkkong/data/pet-locations.json" | python -m json.tool
```

Expected:

```json
{"total": N, "saved": N, "duplicate": 0, "skipped": 0}
```

`saved > 0` 이면 파이프라인 정상 동작 확인 완료.
