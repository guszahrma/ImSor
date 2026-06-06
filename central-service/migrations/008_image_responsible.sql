-- 008_image_responsible.sql
-- Store Image Responsible explicitly per image as a nullable FK to users.
-- Backfills existing images using the single-match Camera rule:
-- if exactly one Camera record matches (camera_make, camera_model), assign that user.

BEGIN;

ALTER TABLE images ADD COLUMN image_responsible_id INTEGER REFERENCES users(id);

-- Backfill: assign where exactly one Camera record matches the image's EXIF make+model.
WITH single_camera AS (
    SELECT make, model, user_id
    FROM cameras
    WHERE (make, model) IN (
        SELECT make, model FROM cameras GROUP BY make, model HAVING COUNT(*) = 1
    )
)
UPDATE images
SET image_responsible_id = sc.user_id
FROM single_camera sc
WHERE images.camera_make = sc.make
  AND images.camera_model = sc.model
  AND images.image_responsible_id IS NULL;

COMMIT;
