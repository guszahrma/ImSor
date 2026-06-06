# ADR-0007: Shared utilities extracted to `shared/` package

## Decision

A `shared/` directory at the repo root contains cross-component Python utilities. Each component that needs it adds `shared/` to its `sys.path`. The first resident is `imsor_utils.py`, containing:

- `extract_exif(file_path: str) -> dict` — EXIF extraction with a path-only signature
- `normalize_path(path: str) -> str` — Windows UNC path normalisation to forward-slash form

The signature of `extract_exif` is path-only. Components that have file data in memory must write the file to disk before calling it.

## Context

Three components — scanner-agent, auto-annotator, and imsor-web — are independently deployed but live in the same monorepo. They had duplicated implementations of `extract_exif` and `normalize_path`:

- `normalize_path` was copied verbatim between scanner-agent and auto-annotator.
- `extract_exif` existed in scanner-agent (path-based) and was re-implemented in imsor-web (bytes-based) when the upload feature was added.

Three alternatives were considered for where to put shared code:

**Inside `auto-annotator/`:** already on imsor-web's `sys.path`. Rejected because the auto-annotator is semantically an annotation tool, not a utility library — and scanner-agent would need to add it to its own path anyway.

**No shared package — live with duplication:** rejected because the EXIF extraction code contains non-obvious logic (orientation degree mapping, GPS DMS conversion, NUL-byte stripping) that must stay in sync. Divergence has already occurred once (bytes vs. path signature).

**`shared/` at repo root (chosen):** neutral ownership, no component is privileged, each consumer adds one `sys.path` line.

## Consequence

- All components that need EXIF extraction or path normalisation import from `shared/imsor_utils.py`.
- Components that read file data into memory before writing (currently: imsor-web upload handler) must write the file to disk first, then call `extract_exif` with the path.
- `shared/` has no `__init__.py` and is not a pip-installable package — it is added to `sys.path` at runtime. If the repo ever splits into separate deployable packages, `shared/` would need to become an installable library.
- The scanner-agent and auto-annotator CLI entry points (`scan.py`, `annotate.py`) remain Windows-only (`msvcrt`). The library modules (`scanner.py`, `detector.py`, `shared/imsor_utils.py`) are cross-platform.
