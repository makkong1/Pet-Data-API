-- v2: 반려동물 시설 (영업장 + 동물병원) 스키마

-- 공통 시설 테이블
CREATE TABLE IF NOT EXISTS pet_facilities (
    id              SERIAL PRIMARY KEY,
    source_id       VARCHAR(100) NOT NULL UNIQUE,
    type            VARCHAR(20)  NOT NULL,  -- HOSPITAL / BUSINESS
    name            VARCHAR(200) NOT NULL,
    status          VARCHAR(30)  NOT NULL,
    address         VARCHAR(300) NOT NULL,
    region_city     VARCHAR(50)  NOT NULL,
    region_district VARCHAR(50)  NOT NULL,
    phone           VARCHAR(20),
    collected_at    TIMESTAMP    DEFAULT NOW()
);

-- 영업장 전용 상세 테이블
CREATE TABLE IF NOT EXISTS business_details (
    id              SERIAL PRIMARY KEY,
    facility_id     INT NOT NULL REFERENCES pet_facilities(id) ON DELETE CASCADE,
    business_type   VARCHAR(50) NOT NULL,  -- 미용/위탁/판매/생산
    registration_no VARCHAR(100)
);

-- 병원 전용 상세 테이블
CREATE TABLE IF NOT EXISTS hospital_details (
    id          SERIAL PRIMARY KEY,
    facility_id INT NOT NULL REFERENCES pet_facilities(id) ON DELETE CASCADE,
    license_no  VARCHAR(100),
    specialty   VARCHAR(100)
);

-- 인덱스
CREATE UNIQUE INDEX IF NOT EXISTS idx_facilities_source_id
    ON pet_facilities(source_id);

CREATE INDEX IF NOT EXISTS idx_facilities_region_type_status
    ON pet_facilities(region_city, region_district, type, status);

CREATE INDEX IF NOT EXISTS idx_facilities_collected_at
    ON pet_facilities(collected_at);

CREATE INDEX IF NOT EXISTS idx_business_details_facility_id
    ON business_details(facility_id);

CREATE INDEX IF NOT EXISTS idx_hospital_details_facility_id
    ON hospital_details(facility_id);
