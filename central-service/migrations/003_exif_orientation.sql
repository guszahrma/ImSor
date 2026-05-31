-- 003_exif_orientation.sql
-- Adds exif_orientation column to images table.
-- Stores the rotation in degrees (0, 90, 180, 270) derived from the EXIF Orientation tag.
-- Missing or unsupported EXIF values default to 0.

ALTER TABLE images ADD COLUMN IF NOT EXISTS exif_orientation INTEGER NOT NULL DEFAULT 0;
