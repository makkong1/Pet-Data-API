-- v3: 시설 인터랙션 로그 — Petory 가 /events/recommendation 으로 보낸 노출/클릭/예약 이벤트.
-- recommendation_log.request_id 와 약결합 (FK 없음, request_id 가 없을 수도 있음).
-- facility_id 는 공공 DB 의 시설일 때만 값 있음. Kakao-only 후보는 source_id 만.

CREATE TABLE IF NOT EXISTS facility_interactions (
    id           BIGSERIAL    PRIMARY KEY,
    request_id   VARCHAR(32),
    facility_id  INT,
    source_id    VARCHAR(100),
    user_ref     VARCHAR(64),
    event        VARCHAR(20)  NOT NULL,
    occurred_at  TIMESTAMPTZ  NOT NULL,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_facility_interactions_facility_event_time
    ON facility_interactions (facility_id, event, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_facility_interactions_request_id
    ON facility_interactions (request_id);

CREATE INDEX IF NOT EXISTS idx_facility_interactions_event_time
    ON facility_interactions (event, occurred_at DESC);
