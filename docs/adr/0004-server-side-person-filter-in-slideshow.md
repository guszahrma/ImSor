# ADR-0004: Server-side person filtering in slideshow queue

## Decision

The slideshow queue endpoint filters images by focus persons (AND/OR logic) on the server. The client sends two lists of person IDs (`and_person_ids`, `or_person_ids`); the server returns only images that satisfy the predicate. The server also returns the largest identified bbox per focus person per image so the client can drive zoom.

## Context

The slideshow applies several filters. Some live on the server (`min_rating`, `min_raters`) and some on the client (year range). When person focus filtering was added, both placements were viable:

**Client-side:** the server returns all qualifying images with a `person_bboxes` map; the browser applies AND/OR logic before displaying. Consistent with how the year filter works; no API change needed for the filter predicate itself.

**Server-side (chosen):** the AND/OR predicate is evaluated on the server; only matching images are returned. Requires passing person ID lists as query params.

The deciding factor is data dependency. Person filtering requires knowing which persons have an identified bbox in each image — information that lives in the `person_identities` table and is not otherwise sent to the client. Evaluating it client-side would require either (a) sending the full identity map for every image in the queue, or (b) a separate prefetch. Both options transfer data the client has no other use for. Server-side evaluation resolves the predicate at the source and returns only what the client needs: matched images plus bbox coordinates for zoom.

The year filter stays client-side because `date_taken` is already present in every queue item for other purposes (age overlay computation). No extra data crosses the wire.

## Consequence

- `slideshow-queue` accepts `and_person_ids` and `or_person_ids` as comma-separated query params (empty = no person filter).
- The response includes `person_bboxes: {person_id: {x, y, width, height} | null}` for each focus person per image. This is used solely for zoom animation on the client.
- Adding a new person to the focus list or changing AND/OR mode requires clicking "Apply & reload" to fetch a new queue from the server. Zoom and age display toggles remain instant (client-side).
- If the person identity data ever becomes available client-side for other reasons, the filter could be moved to the client without changing the API contract — `person_bboxes` would still carry all the data needed.
