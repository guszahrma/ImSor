#!/usr/bin/env python3
"""
Cleanup: deletes redundant duplicate images from disk and database.

    python scripts/cleanup.py            # dry run — reports what would happen
    python scripts/cleanup.py --execute  # actually deletes files and DB records

Rules (see ADR-0009):
  - 1 vote sufficient to mark an image redundant
  - Clusters with conflicting votes (users disagree on original) are skipped
  - Clusters where the original file is missing from disk are skipped
  - Annotations on redundant images are deleted without migration
"""

import argparse
import subprocess
import sys
import tempfile
import os
from collections import defaultdict
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "imsor-web"))

import config


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

DB_CONTAINER = "imsor-dev-db"
DB_USER = "imsor"
DB_NAME = "imsor"


def _psql_args():
    return ["docker", "exec", DB_CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME]


def psql_query(sql):
    """Run a SELECT and return list of row-tuples (all values as strings)."""
    result = subprocess.run(
        _psql_args() + ["-t", "-A", "-F", "|", "-c", sql],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"psql error: {result.stderr.strip()}")
    rows = []
    for line in result.stdout.strip().splitlines():
        if line:
            rows.append(tuple(line.split("|")))
    return rows


def psql_file(sql):
    """Execute a multi-statement SQL string via a temp file copied into the container."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
        f.write(sql)
        tmp_local = f.name
    try:
        subprocess.run(
            ["docker", "cp", tmp_local, f"{DB_CONTAINER}:/tmp/_cleanup.sql"],
            check=True, capture_output=True,
        )
        result = subprocess.run(
            _psql_args() + ["-f", "/tmp/_cleanup.sql"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"psql error: {result.stderr.strip()}")
        return result.stdout
    finally:
        os.unlink(tmp_local)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def resolve_path(stored_path: str) -> str:
    p = PurePosixPath(stored_path)
    for prefix, mount in config.path_mappings.items():
        try:
            rel = p.relative_to(PurePosixPath(prefix))
            return str(Path(mount) / rel)
        except ValueError:
            continue
    return stored_path


# ---------------------------------------------------------------------------
# Union-find
# ---------------------------------------------------------------------------

def build_clusters(pairs):
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    for a, b in pairs:
        union(a, b)

    groups = {}
    for a, b in pairs:
        for x in (a, b):
            groups.setdefault(find(x), set()).add(x)
    return groups


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Delete redundant duplicate images from disk and database."
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="Commit deletions. Without this flag the script is a dry run.",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print every file that would be / was deleted.",
    )
    args = parser.parse_args()
    dry_run = not args.execute

    if dry_run:
        print("DRY RUN — no changes will be made. Pass --execute to commit.\n")

    # ── Load data ────────────────────────────────────────────────────────────
    print("Loading duplicate pairs...")
    pairs = [(int(r[0]), int(r[1])) for r in psql_query(
        "SELECT image_a_id, image_b_id FROM duplicate_pairs")]
    if not pairs:
        print("No duplicate pairs found. Nothing to do.")
        return
    clusters = build_clusters(pairs)
    print(f"  {len(pairs)} pairs → {len(clusters)} clusters")

    print("Loading image paths...")
    path_by_id = {int(r[0]): r[1] for r in psql_query(
        "SELECT id, file_path FROM images")}

    print("Loading duplicate_role votes...")
    vote_rows = psql_query("""
        SELECT DISTINCT ON (image_id, user_id) image_id, user_id, value
        FROM annotations WHERE annotation_type = 'duplicate_role'
        ORDER BY image_id, user_id, id DESC
    """)
    # votes[image_id][user_id] = designated_original_id
    votes: dict[int, dict[int, int]] = defaultdict(dict)
    for image_id, user_id, value in vote_rows:
        votes[int(image_id)][int(user_id)] = int(value)

    # ── Classify clusters ────────────────────────────────────────────────────
    to_delete: list[tuple[int, int, str]] = []   # (img_id, original_id, stored_path)
    skipped_no_votes: list[list[int]] = []
    skipped_conflict: list[list[int]] = []
    skipped_missing_original: list[tuple[int, str]] = []

    for root, members in clusters.items():
        member_list = sorted(members)

        # Collect which image each user designated as original in this cluster
        user_originals: dict[int, int] = {}  # user_id -> original_image_id
        for img_id in member_list:
            for uid, val in votes.get(img_id, {}).items():
                if val == img_id:
                    user_originals[uid] = img_id

        if not user_originals:
            skipped_no_votes.append(member_list)
            continue

        designated = set(user_originals.values())
        if len(designated) > 1:
            skipped_conflict.append(member_list)
            continue

        original_id = next(iter(designated))

        original_local = resolve_path(path_by_id.get(original_id, ""))
        if not Path(original_local).exists():
            skipped_missing_original.append((original_id, original_local))
            continue

        for img_id in member_list:
            if img_id != original_id:
                to_delete.append((img_id, original_id, path_by_id.get(img_id, "")))

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'=' * 62}")
    print(f"  Images to delete:              {len(to_delete):>6}")
    print(f"  Skipped — no votes:            "
          f"{sum(len(m) for m in skipped_no_votes):>6} images in "
          f"{len(skipped_no_votes)} clusters")
    print(f"  Skipped — conflicting votes:   "
          f"{sum(len(m) for m in skipped_conflict):>6} images in "
          f"{len(skipped_conflict)} clusters")
    print(f"  Skipped — original missing:    "
          f"{sum(1 for _ in skipped_missing_original):>6} clusters")
    print(f"{'=' * 62}")

    if skipped_conflict:
        print("\nConflicted clusters (manual resolution needed):")
        for members in skipped_conflict:
            print(f"  images: {members}")

    if skipped_missing_original:
        print("\nClusters skipped — original file not found on disk:")
        for orig_id, orig_path in skipped_missing_original:
            print(f"  image #{orig_id}: {orig_path}")

    if args.verbose:
        print("\nFiles to delete:")
        for img_id, original_id, stored_path in to_delete:
            print(f"  #{img_id} → redundant of #{original_id}: {stored_path}")

    if dry_run:
        print("\nDry run complete. Pass --execute to delete.")
        return

    if not to_delete:
        print("\nNothing to delete.")
        return

    # ── Delete files from disk ───────────────────────────────────────────────
    print(f"\nDeleting {len(to_delete)} files from disk...")
    deleted_files = 0
    missing_files = 0
    failed_files = []
    delete_ids = []

    for img_id, original_id, stored_path in to_delete:
        local_path = resolve_path(stored_path)
        p = Path(local_path)
        if p.exists():
            try:
                p.unlink()
                deleted_files += 1
            except OSError as e:
                print(f"  WARN: could not delete {local_path}: {e}")
                failed_files.append(img_id)
                continue
        else:
            missing_files += 1
        delete_ids.append(img_id)

    print(f"  Deleted from disk: {deleted_files}")
    print(f"  Already missing:   {missing_files}")
    if failed_files:
        print(f"  Failed (kept in DB): {len(failed_files)}")

    if not delete_ids:
        print("No DB records to remove.")
        return

    # ── Delete DB records ────────────────────────────────────────────────────
    print(f"\nDeleting {len(delete_ids)} records from database...")
    ids = "ARRAY[" + ",".join(str(i) for i in delete_ids) + "]"

    sql = f"""
BEGIN;

DELETE FROM person_bbox_dismissals
WHERE bbox_annotation_id IN (
    SELECT id FROM annotations WHERE image_id = ANY({ids})
);

DELETE FROM person_identities
WHERE bbox_annotation_id IN (
    SELECT id FROM annotations WHERE image_id = ANY({ids})
);

DELETE FROM annotations WHERE image_id = ANY({ids});

DELETE FROM sharing_permissions WHERE image_id = ANY({ids});

DELETE FROM duplicate_pairs
WHERE image_a_id = ANY({ids}) OR image_b_id = ANY({ids});

DELETE FROM images WHERE id = ANY({ids});

COMMIT;
"""
    output = psql_file(sql)
    # Print row counts from psql output
    for line in output.strip().splitlines():
        if line.startswith("DELETE") or line in ("BEGIN", "COMMIT"):
            print(f"  {line}")

    print(f"\nDone. {len(delete_ids)} images removed from disk and database.")


if __name__ == "__main__":
    main()
