-- v3: 트렌드 키워드 일별 스냅샷 (시계열)
-- Redis 는 핫 캐시 역할, Postgres 는 시계열·증감률·랭커 신호용.

CREATE TABLE IF NOT EXISTS trend_snapshots (
    id            BIGSERIAL PRIMARY KEY,
    snapshot_date DATE         NOT NULL,
    category      VARCHAR(30)  NOT NULL,
    keyword       VARCHAR(200) NOT NULL,
    score         INT          NOT NULL,
    collected_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (snapshot_date, category, keyword)
);

CREATE INDEX IF NOT EXISTS idx_trend_snapshots_category_date
    ON trend_snapshots (category, snapshot_date DESC);

CREATE INDEX IF NOT EXISTS idx_trend_snapshots_keyword_date
    ON trend_snapshots (keyword, snapshot_date DESC);
