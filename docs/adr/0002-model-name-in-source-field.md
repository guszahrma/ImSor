# ADR-0002: AI model name encoded in the annotation source field

## Decision

AI-generated `person_bbox` annotations store the model name inside the `source` field using the format `"ai:<model>"` (e.g. `"ai:yolov8x"`), rather than in a separate column.

## Context

We needed to record which YOLO model produced each bounding box annotation so that the annotations page can filter to show only images annotated by the currently active model. Two options were considered:

1. Add a `model_name` column to the `annotations` table — clean separation but requires a schema migration and adds a column that is only meaningful for AI annotations.
2. Encode the model name in the existing `source` field — no schema change, source already distinguishes AI from manual, and the model name is part of that provenance.

We chose option 2. The `source` field already carries the meaning "who or what produced this annotation." Extending it to `"ai:yolov8x"` is a natural elaboration of that meaning.

## Consequence

Code that checks `source == "ai"` must be updated to `source.startswith("ai")`. Existing annotations stored as plain `"ai"` are treated as produced by an unknown model and will not appear in model-filtered views until re-annotated.
