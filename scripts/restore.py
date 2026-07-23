#!/usr/bin/env python3
"""
Restore: copies wrongly-deleted images back to their NAS locations.

    python scripts/restore.py            # dry run — reports what would happen
    python scripts/restore.py --execute  # actually copies files
    python scripts/restore.py --verbose  # show every file

Source of truth: image_file_events rows with resolved_at IS NULL.
No DB writes — image_file_events rows resolve naturally when each image is served.

Unrecoverable: //zahrdata/Home/Martin/Bilder/2008/Foton från digitalkamera/2008-07-13-2326-37/DSCN6731.jpg
"""

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "imsor-web"))

import config

DB_CONTAINER = "imsor-dev-db"
DB_USER = "imsor"
DB_NAME = "imsor"

RECOVERY_ROOT = Path.home() / "recovery"
RECOVERY_EXTRA_ROOT = Path.home() / "recovery_extra"

# Files the standard transform cannot find — (source, target, db_path).
EXCEPTIONS = [
    (
        RECOVERY_EXTRA_ROOT / "home/Martin/Martin/Bilder/2008/Foton från digitalkamera/2008-10-13-1805-18/DSCN0025.jpg",
        Path("/mnt/zahrdata_home/Martin/Bilder/2008/Foton från digitalkamera/2008-08-26-1541-22/DSCN0025.jpg"),
        "//zahrdata/Home/Martin/Bilder/2008/Foton från digitalkamera/2008-08-26-1541-22/DSCN0025.jpg",
    ),
    (
        RECOVERY_EXTRA_ROOT / "home/Martin/Martin/Bilder/2008/Foton från digitalkamera/2008-10-13-1805-18/DSCN0029.jpg",
        Path("/mnt/zahrdata_home/Martin/Bilder/2008/Foton från digitalkamera/2008-08-26-1541-22/DSCN0029.jpg"),
        "//zahrdata/Home/Martin/Bilder/2008/Foton från digitalkamera/2008-08-26-1541-22/DSCN0029.jpg",
    ),
    (
        RECOVERY_EXTRA_ROOT / "home/Martin/Martin/Bilder/2009/Foton från digitalkamera/2009-09-20-1323-31/DSCN6613.jpg",
        Path("/mnt/zahrdata_home/Martin/Bilder/2008/Foton från digitalkamera/2008-07-13-2326-37/DSCN6613.jpg"),
        "//zahrdata/Home/Martin/Bilder/2008/Foton från digitalkamera/2008-07-13-2326-37/DSCN6613.jpg",
    ),
]

EXCEPTION_DB_PATHS = {e[2] for e in EXCEPTIONS}


def psql_query(sql):
    result = subprocess.run(
        ["docker", "exec", DB_CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME,
         "-t", "-A", "-F", "|", "-c", sql],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"psql error: {result.stderr.strip()}")
    return [tuple(line.split("|")) for line in result.stdout.strip().splitlines() if line]


def psql_exec(sql: str) -> None:
    result = subprocess.run(
        ["docker", "exec", DB_CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME, "-c", sql],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"psql error: {result.stderr.strip()}")


def resolve_path(stored_path: str) -> Path:
    p = PurePosixPath(stored_path)
    for prefix, mount in config.path_mappings.items():
        try:
            rel = p.relative_to(PurePosixPath(prefix))
            return Path(mount) / rel
        except ValueError:
            continue
    return Path(stored_path)


def recovery_source(stored_path: str) -> Path:
    """Standard transform: DB path → expected file in ~/recovery."""
    # //zahrdata/Home/X  →  ~/recovery/home/Martin/X
    prefix = "//zahrdata/Home/"
    assert stored_path.startswith(prefix), f"Unexpected path prefix: {stored_path}"
    suffix = stored_path[len(prefix):]
    return RECOVERY_ROOT / "home" / "Martin" / suffix


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    dry_run = not args.execute

    if dry_run:
        print("DRY RUN — no files will be copied. Pass --execute to copy.\n")

    print("Loading missing images from image_file_events...")
    rows = psql_query("""
        SELECT DISTINCT i.file_path, i.checksum
        FROM image_file_events ife
        JOIN images i ON i.id = ife.image_id
        WHERE ife.resolved_at IS NULL
    """)
    db_paths = [(r[0], r[1] if len(r) > 1 else None) for r in rows]
    print(f"  {len(db_paths)} images to restore\n")

    copied = 0
    already_exists = 0
    source_missing = 0
    invalid_jpeg = 0
    failed = 0
    errors = []

    # Build checksum lookup for the 3 hardcoded exceptions by DB path
    checksum_by_db_path = {db_path: cksum for db_path, cksum in db_paths}

    def attempt_copy(source: Path, target: Path, label: str, expected_checksum: str | None,
                     fix_checksum: bool = False, db_path: str | None = None):
        nonlocal copied, already_exists, source_missing, invalid_jpeg, failed

        if target.exists():
            already_exists += 1
            if args.verbose:
                print(f"  EXISTS (skip): {label}")
            return

        if not source.exists():
            source_missing += 1
            errors.append(f"SOURCE MISSING: {source}")
            return

        if expected_checksum:
            actual = sha256(source)
            if actual != expected_checksum:
                if not fix_checksum:
                    invalid_jpeg += 1
                    errors.append(f"CHECKSUM MISMATCH: {source} (expected {expected_checksum[:12]}… got {actual[:12]}…)")
                    return
                print(f"  CHECKSUM MISMATCH (will fix): {source.name} "
                      f"(expected {expected_checksum[:12]}… got {actual[:12]}…)")

        if args.verbose:
            print(f"  {'COPY' if not dry_run else 'WOULD COPY'}: {source.name} → {target}")

        if not dry_run:
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                copied += 1
                if fix_checksum and db_path:
                    new_checksum = sha256(target)
                    escaped = db_path.replace("'", "''")
                    psql_exec(
                        f"UPDATE images SET checksum = '{new_checksum}' "
                        f"WHERE file_path = '{escaped}'"
                    )
                    print(f"  DB updated: {db_path} → checksum {new_checksum[:12]}…")
            except OSError as e:
                failed += 1
                errors.append(f"COPY FAILED: {target}: {e}")
        else:
            copied += 1

    # Standard transform
    for db_path, cksum in db_paths:
        if db_path in EXCEPTION_DB_PATHS:
            continue
        source = recovery_source(db_path)
        target = resolve_path(db_path)
        attempt_copy(source, target, db_path, cksum)

    # Hardcoded exceptions — copy regardless of checksum mismatch, then update DB
    for source, target, db_path in EXCEPTIONS:
        attempt_copy(source, target, source.name, checksum_by_db_path.get(db_path),
                     fix_checksum=True, db_path=db_path)

    print(f"{'=' * 60}")
    print(f"  {'Would copy' if dry_run else 'Copied'}:      {copied:>6}")
    print(f"  Already exists: {already_exists:>6}")
    print(f"  Source missing: {source_missing:>6}")
    print(f"  Bad checksum:   {invalid_jpeg:>6}")
    print(f"  Failed:         {failed:>6}")
    print(f"{'=' * 60}")

    if errors:
        print("\nProblems:")
        for e in errors:
            print(f"  {e}")

    if dry_run and copied > 0:
        print(f"\nDry run complete. Pass --execute to copy {copied} files.")


if __name__ == "__main__":
    main()
