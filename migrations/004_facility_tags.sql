-- v3: 시설 태그 (검색 깊이 보조)
-- 단일 시설에 여러 태그를 비정규화로 붙여 카테고리 외 키워드/시술/메뉴 필터를 지원.
-- source 는 태그 출처(공공 데이터·블로그 멘션·관리자 수동) 추적용.

CREATE TABLE IF NOT EXISTS facility_tags (
    facility_id INT          NOT NULL REFERENCES pet_facilities(id) ON DELETE CASCADE,
    tag         VARCHAR(50)  NOT NULL,
    source      VARCHAR(20)  NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (facility_id, tag, source)
);

CREATE INDEX IF NOT EXISTS idx_facility_tags_facility
    ON facility_tags (facility_id);

CREATE INDEX IF NOT EXISTS idx_facility_tags_tag_trgm
    ON facility_tags USING gin (lower(tag) gin_trgm_ops);
