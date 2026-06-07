-- 009_image_file_events.sql
-- One row per /serve request where the file was not found on disk.
-- resolved_at is set when the file becomes accessible again.

BEGIN;

CREATE TABLE image_file_events (
    id          SERIAL PRIMARY KEY,
    image_id    INTEGER NOT NULL REFERENCES images(id),
    detected_at TIMESTAMP NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMP
);

CREATE INDEX idx_image_file_events_image_id ON image_file_events(image_id);

COMMIT;
