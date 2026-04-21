ALTER TABLE pet_facilities
    ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS lng DOUBLE PRECISION;

CREATE INDEX IF NOT EXISTS idx_facilities_coords
    ON pet_facilities (lat, lng)
    WHERE lat IS NOT NULL;
