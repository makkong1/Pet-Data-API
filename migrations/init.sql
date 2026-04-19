-- pg_trgm 확장 (한국어 포함 trigram 유사도 검색)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 유기동물 테이블
CREATE TABLE IF NOT EXISTS abandoned_animals (
    id          SERIAL PRIMARY KEY,
    notice_no   VARCHAR(100) NOT NULL UNIQUE,
    animal_type VARCHAR(20),
    breed       VARCHAR(100),
    age         VARCHAR(50),
    gender      VARCHAR(10),
    region      VARCHAR(100),
    shelter_name VARCHAR(200),
    status      VARCHAR(30),
    notice_date DATE,
    collected_at TIMESTAMP DEFAULT NOW()
);

-- 수집 로그 테이블
CREATE TABLE IF NOT EXISTS collection_logs (
    id            SERIAL PRIMARY KEY,
    source        VARCHAR(100) NOT NULL,
    status        VARCHAR(20)  NOT NULL,
    total_fetched INT          DEFAULT 0,
    total_saved   INT          DEFAULT 0,
    error_message TEXT,
    started_at    TIMESTAMP    NOT NULL,
    finished_at   TIMESTAMP
);

-- 인덱스
CREATE UNIQUE INDEX IF NOT EXISTS idx_animals_notice_no
    ON abandoned_animals(notice_no);

CREATE INDEX IF NOT EXISTS idx_animals_region_status_type
    ON abandoned_animals(region, status, animal_type);

CREATE INDEX IF NOT EXISTS idx_animals_notice_date
    ON abandoned_animals(notice_date);

CREATE INDEX IF NOT EXISTS idx_animals_breed_trgm
    ON abandoned_animals USING gin(breed gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_animals_shelter_trgm
    ON abandoned_animals USING gin(shelter_name gin_trgm_ops);

-- Materialized View (통계)
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_region_stats AS
SELECT
    region,
    DATE(notice_date)                                    AS date,
    COUNT(*)                                             AS total_count,
    COUNT(*) FILTER (WHERE status = '입양')              AS adopted_count,
    COUNT(*) FILTER (WHERE status = '안락사')            AS euthanized_count
FROM abandoned_animals
GROUP BY region, DATE(notice_date);

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_region_stats_region_date
    ON mv_region_stats(region, date);
