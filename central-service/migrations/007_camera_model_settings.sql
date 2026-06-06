-- 007_camera_model_settings.sql
-- Per-(make, model) EXIF rotation override settings.
-- skip_exif_rotation=TRUE means pixels are already correctly oriented; ignore EXIF tag.

BEGIN;

CREATE TABLE camera_model_settings (
    id SERIAL PRIMARY KEY,
    make VARCHAR(200) NOT NULL,
    model VARCHAR(200) NOT NULL,
    skip_exif_rotation BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (make, model)
);

COMMIT;
