# ADR-0008: Explicit Image Responsible Storage

## Status
Accepted

## Context
Image Responsible was not stored anywhere in the database. For scanner-registered images it was implicitly derivable from Camera records (EXIF make/model → Camera → User), but this derivation was fragile: changing a Camera record would silently change all past attributions, and ambiguous cases (multiple Camera records for the same make/model, or no Camera record at all) had no resolution path. Folder Attribution was planned as a resolution mechanism but was never implemented. For uploaded images, the uploader was encoded only in the file path, not in the database.

## Decision
Store Image Responsible explicitly as `image_responsible_id` — a nullable foreign key to the `users` table — on each image record.

**Assignment rules:**
- **Scanner-registered images:** central-service resolves attribution at registration time. If exactly one Camera record matches the image's EXIF (make, model), that User is assigned. If zero or multiple Camera records match, `image_responsible_id` is left NULL.
- **Uploaded images:** the uploading user is assigned unconditionally.
- **Camera Assignment trigger:** when a Camera record is created, central-service retroactively fills `image_responsible_id = NULL` on all matching images — but only if exactly one Camera record now exists for that (make, model). Non-NULL attributions are never overwritten by this trigger.
- **Camera Assignment deletion:** existing `image_responsible_id` values are not cleared.
- **Manual override:** a Superuser may assign or reassign Image Responsible on any image via the Attribution Management page.
- **Migration backfill:** the migration that adds the column applies the single-match rule to all existing images immediately.

## Alternatives Considered
- **Derive at query time from Camera + Folder Attribution:** requires Folder Attribution to be fully implemented; silently mutates all historical attributions when Camera records change; ambiguous cases have no stable representation.
- **Store on first match (even if ambiguous):** wrong attribution is worse than NULL — it misleads both the access model and the user.

## Consequences
- Image Responsible is a stable, queryable fact on each image, unaffected by future Camera record changes.
- A one-time migration backfill is required at deploy time.
- Images that remain NULL after backfill are surfaced via the Attribution Management page for Superuser resolution.
- The planned Folder Attribution mechanism is superseded by this design and the manual override page.
