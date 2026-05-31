# ADR-0001: Rotation Correction is additive on top of EXIF Orientation

## Decision

Display Rotation = (EXIF Orientation + Rotation Correction) % 360.

A user-set Rotation Correction adds to the EXIF Orientation rather than replacing it.

## Context

Images have two sources of rotation information: EXIF Orientation (read from the file at scan time) and Rotation Correction (set by a user). We needed to decide whether the user correction is a delta on top of EXIF or an absolute override that ignores EXIF entirely.

We chose additive because it lets a user correct the residual error without needing to know what EXIF says. If EXIF already handles 90° and the image is still slightly wrong, the user only needs to think about the remaining delta.

## Consequence

If a scanner upgrade changes how EXIF Orientation is read for existing images (e.g. from always-0° to the actual EXIF value), existing Rotation Corrections will shift the Display Rotation by an unintended amount. Any such scanner upgrade must be accompanied by a migration that clears or recalculates existing Rotation Correction annotations.
