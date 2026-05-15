-- v3: 추천 요청 로그 — /recommend 호출 마다 어떤 시설을 어떤 점수로 노출했는지 기록.
-- /events/recommendation 콜백을 같은 request_id 로 연결해 노출→클릭 환류 분석 가능.

CREATE TABLE IF NOT EXISTS recommendation_log (
    id                BIGSERIAL    PRIMARY KEY,
    request_id        VARCHAR(32)  NOT NULL UNIQUE,
    requested_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    context           VARCHAR(30),
    lat               DOUBLE PRECISION,
    lng               DOUBLE PRECISION,
    radius_km         REAL,
    top_n             INT,
    pet_payload       JSONB,
    facility_ids      INT[],
    facility_scores   REAL[],
    recommend_version VARCHAR(40)
);

CREATE INDEX IF NOT EXISTS idx_recommendation_log_requested_at
    ON recommendation_log (requested_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_log_context_date
    ON recommendation_log (context, requested_at DESC);
