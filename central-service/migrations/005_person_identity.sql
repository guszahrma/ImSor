-- 005_person_identity.sql
-- Separates person detection (spatial, AI-owned) from person identification (identity, user-owned).
-- Introduces Detection Adoptions, person_identities, and person_bbox_dismissals.

BEGIN;

-- ── 1. New tables ─────────────────────────────────────────────────────────────

CREATE TABLE person_identities (
    id                  SERIAL PRIMARY KEY,
    bbox_annotation_id  INTEGER NOT NULL REFERENCES annotations(id) ON DELETE CASCADE,
    person_id           INTEGER REFERENCES persons(id),
    user_id             INTEGER REFERENCES users(id),
    created_at          TIMESTAMP DEFAULT NOW()
);

-- bbox_annotation_id here references the AI detection (not a user copy)
CREATE TABLE person_bbox_dismissals (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES users(id),
    bbox_annotation_id  INTEGER NOT NULL REFERENCES annotations(id) ON DELETE CASCADE,
    created_at          TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_dismissal_user_bbox UNIQUE (user_id, bbox_annotation_id)
);

-- ── 2. Migrate unique person names into the persons table ─────────────────────

INSERT INTO persons (name)
SELECT DISTINCT value::jsonb->>'person_name'
FROM annotations
WHERE annotation_type = 'person_bbox'
  AND value::jsonb->>'person_name' IS NOT NULL
  AND value::jsonb->>'person_name' <> ''
  AND value::jsonb->>'person_name' <> '????'
ON CONFLICT (name) DO NOTHING;

-- ── 3. Create Detection Adoptions + Person Identifications ────────────────────
-- All existing named person_bbox annotations are attributed to user 2.
-- "????" annotations become adoptions with person_id = NULL.

WITH source_bboxes AS (
    SELECT
        id                                      AS original_id,
        image_id,
        value::jsonb->>'person_name'            AS person_name,
        (value::jsonb->>'x')::float             AS x,
        (value::jsonb->>'y')::float             AS y,
        (value::jsonb->>'width')::float         AS width,
        (value::jsonb->>'height')::float        AS height,
        (value::jsonb->>'confidence')::float    AS confidence
    FROM annotations
    WHERE annotation_type = 'person_bbox'
      AND value::jsonb->>'person_name' IS NOT NULL
      AND value::jsonb->>'person_name' <> ''
),
new_adoptions AS (
    INSERT INTO annotations (image_id, user_id, annotation_type, value, source, created_at)
    SELECT
        sb.image_id,
        2,
        'person_bbox',
        jsonb_build_object(
            'inherited_from', sb.original_id,
            'x',              sb.x,
            'y',              sb.y,
            'width',          sb.width,
            'height',         sb.height,
            'confidence',     sb.confidence
        )::text,
        'manual',
        NOW()
    FROM source_bboxes sb
    RETURNING id, (value::jsonb->>'inherited_from')::int AS original_id
)
INSERT INTO person_identities (bbox_annotation_id, person_id, user_id, created_at)
SELECT
    na.id,
    CASE WHEN sb.person_name = '????' THEN NULL ELSE p.id END,
    2,
    NOW()
FROM new_adoptions na
JOIN source_bboxes sb ON sb.original_id = na.original_id
LEFT JOIN persons p ON p.name = sb.person_name;

-- ── 4. Strip person_name from all person_bbox JSON values ─────────────────────

UPDATE annotations
SET value = (value::jsonb - 'person_name')::text
WHERE annotation_type = 'person_bbox'
  AND value::jsonb ? 'person_name';

COMMIT;
