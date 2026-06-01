# ADR-0003: Copy-on-identify for person bbox ownership

## Decision

When a user connects a Person Detection to a Person, the system creates a new user-owned `person_bbox` annotation (a Detection Adoption) that inherits from the AI detection via `inherited_from` in the JSON value. The AI detection is never mutated. Identity assertions (Person Identifications) are stored in a dedicated `person_identities` table referencing the Detection Adoption, not the AI detection.

## Context

The original model stored both bbox geometry and person identity in a single `person_bbox` annotation owned by the AI. When a user assigned a name, the annotation was PATCHed in place — overwriting the AI's record and leaving no trace of who made the change or when.

Two alternatives were considered:

**Mutate in place:** update the AI annotation's value with `person_name` and `user_id`. Simple, but loses provenance, prevents multiple users from holding independent beliefs, and conflates a spatial claim (where is the person) with an identity claim (who is the person).

**Separate identity table only:** keep AI bboxes untouched, store identity in a `person_identities` table referencing the AI annotation. Cleaner, but means the user can never adjust the bbox geometry as their own — all geometry corrections would mutate the shared AI record.

**Copy-on-identify (chosen):** the user creates their own version of the detection. This gives each user a row they own and can update (geometry), while identity history is tracked separately in `person_identities` (append-only). The AI detection remains immutable.

## Consequence

- Each user's Detection Adoption is the authoritative source for that user's spatial belief about a detection. Geometry updates upsert this row.
- Person Identifications are append-only and reference the Detection Adoption, not the AI annotation. The latest row per user per adoption is the user's current identity belief.
- Display logic must join the user's own Detection Adoption when rendering bboxes, falling back to the AI detection when no adoption exists.
- The `inherited_from` value in the JSON is not a database-enforced FK. If the AI detection is hard-deleted (after 5 dismissals with no adoptions), any existing Detection Adoptions retain a dangling `inherited_from` reference. This is acceptable since adoptions imply at least one user confirmed the detection.
