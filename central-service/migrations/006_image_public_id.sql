-- 006_image_public_id.sql
-- Adds a stable UUID per image for shareable deep-link URLs.
-- Integer PKs and all FKs are unchanged; this is a secondary identifier only.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE images
    ADD COLUMN public_id UUID NOT NULL DEFAULT gen_random_uuid();

CREATE UNIQUE INDEX uq_images_public_id ON images (public_id);

COMMIT;
