-- v7: pet_facilities.category 컬럼 추가
ALTER TABLE pet_facilities
    ADD COLUMN IF NOT EXISTS category VARCHAR(30);

-- 기존 데이터 백필
UPDATE pet_facilities SET category = 'hospital' WHERE type = 'HOSPITAL' AND category IS NULL;
UPDATE pet_facilities SET category = 'grooming' WHERE type = 'BUSINESS' AND category IS NULL;

CREATE INDEX IF NOT EXISTS idx_facilities_category
    ON pet_facilities (category)
    WHERE category IS NOT NULL;
