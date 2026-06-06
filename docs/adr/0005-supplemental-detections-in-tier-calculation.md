# ADR-0005: Include Supplemental Detections in the Person Annotation Queue tier calculation

## Decision

The Person Annotation Queue tier calculation counts all bboxes on an image — both AI Person Detections and Supplemental Detections — when determining how many bboxes are linked to a Person. A bbox is a bbox regardless of origin.

## Context

The original tier calculation counted only AI Person Detections and their Detection Adoptions. Supplemental Detections (user-drawn bboxes with no `inherited_from`) were invisible to the tier: an image where a user had manually drawn and identified a person would still appear as tier 1 ("no bboxes linked by anyone"), because the identification lived on a Supplemental Detection that the tier logic never examined.

Two alternatives were considered:

**Keep tier AI-detection-only, add a separate indicator:** the tier retains its original meaning (coverage of AI-detected persons), and a separate signal (e.g. a badge or secondary sort key) communicates that supplemental work exists on the image. Keeps the tier definition clean and unchanged; does not reorder the existing queue.

**Fold Supplemental Detections into the tier (chosen):** the tier is redefined to mean coverage of all bboxes on the image. An image where any bbox is unlinked is genuinely incomplete, regardless of who drew it. The alternative indicator approach would require a new UI concept and still leaves the queue misleadingly ordered — an image the annotator has already worked on surfaces at tier 1 as if untouched.

The deciding factor is that the tier exists to communicate how much annotation work remains on an image. A Supplemental Detection that is unlinked is work remaining; one that is linked is work done. Excluding Supplemental Detections from the count misrepresents both cases.

## Consequence

- The total bbox count per image in the tier calculation = AI Person Detections + Supplemental Detections.
- "Linked" means the bbox has a PersonIdentity with a non-null `person_id` — the same criterion for both bbox types.
- For AI Person Detections, the PersonIdentity chain runs through the user's Detection Adoption. For Supplemental Detections, it references the Supplemental Detection directly.
- Multi-user linking of Supplemental Detections (can user B identify a bbox drawn by user A?) is deferred — only one annotator exists at the time of this decision.
- Five legacy Supplemental Detections carry a `person_name` string in their annotation value but have no PersonIdentity row. These must be migrated to proper PersonIdentity rows before the tier calculation is changed, so the tier has a single clean "linked" signal.
