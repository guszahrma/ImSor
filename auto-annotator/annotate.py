import argparse
import json
import msvcrt
import os
import platform
import re
import subprocess
import signal
import sys
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from imsor_utils import normalize_path  # noqa: E402

from api_client import ApiClient
from detector import detect_people
from config import image_extensions, server_urls, yolo_model


# --- Graceful stop / pause state ---
_stop_requested = False
_paused = False


def _handle_sigint(sig, frame):
    global _stop_requested
    if _stop_requested:
        print("\nForce quit.")
        sys.exit(1)
    _stop_requested = True
    print("\n  Stop requested — finishing current file, then stopping.")
    print("  Press Ctrl+C again to force quit.")


signal.signal(signal.SIGINT, _handle_sigint)


def _check_keyboard():
    """Check for pause (P) or quit (Q) key presses without blocking."""
    global _paused, _stop_requested
    while msvcrt.kbhit():
        key = msvcrt.getch().lower()
        if key == b'p':
            _paused = not _paused
            if _paused:
                print("\n  PAUSED — press P to resume, Q to quit.")
            else:
                print("  Resuming...")
        elif key == b'q':
            _stop_requested = True
            _paused = False
            print("\n  Quit requested — finishing current file, then stopping.")

    if _paused:
        while _paused and not _stop_requested:
            if msvcrt.kbhit():
                key = msvcrt.getch().lower()
                if key == b'p':
                    _paused = False
                    print("  Resuming...")
                elif key == b'q':
                    _stop_requested = True
                    _paused = False
                    print("  Quit requested — stopping.")


def _is_bare_server(path: str) -> bool:
    return bool(re.match(r'^\\\\[^\\]+\\?$', path))


def _enumerate_shares(server: str) -> list[str]:
    server = server.rstrip("\\")
    try:
        result = subprocess.run(
            ["net", "view", server],
            capture_output=True, text=True, timeout=30
        )
    except Exception as e:
        print(f"ERROR: Failed to enumerate shares on {server}: {e}")
        sys.exit(1)

    if result.returncode != 0:
        print(f"ERROR: 'net view {server}' failed:")
        print(f"  {result.stderr.strip()}")
        sys.exit(1)

    shares = []
    in_table = False
    for line in result.stdout.splitlines():
        if line.startswith("---"):
            in_table = True
            continue
        if in_table:
            if not line.strip():
                break
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "Disk":
                share_name = parts[0]
                if not share_name.endswith("$"):
                    shares.append(f"{server}\\{share_name}")

    return shares


def find_images(path: str) -> list[str]:
    """Find all image files under a path (recursive)."""
    if os.path.isfile(path):
        ext = os.path.splitext(path)[1].lower()
        if ext in {e.lower() for e in image_extensions}:
            return [path]
        return []

    ext_set = {ext.lower() for ext in image_extensions}
    found = []
    for root, _dirs, files in os.walk(path):
        for name in files:
            if os.path.splitext(name)[1].lower() in ext_set:
                found.append(os.path.join(root, name))
    return found


def _annotate_folder(folder: str, annotation_type: str, client: ApiClient) -> dict:
    """Process all images in a folder and return summary counts."""
    print(f"Scanning {folder} for images...")
    local_files = find_images(folder)
    print(f"  {len(local_files)} image files found")

    annotated_count = 0
    skipped_count = 0
    no_detections_count = 0
    error_count = 0
    total_people = 0

    for i, file_path in enumerate(local_files, 1):
        _check_keyboard()
        if _stop_requested:
            print(f"\n  Stopped at file {i}/{len(local_files)}.")
            break

        print(f"  [{i}/{len(local_files)}] {file_path} ... ", end="", flush=True)

        try:
            # Look up image in central service (normalize path to forward-slash UNC format)
            image_record = client.get_image_by_path(normalize_path(file_path))
            if not image_record:
                print("not registered (skipped)")
                skipped_count += 1
                continue

            image_id = image_record["id"]

            # Check if already annotated with this type
            existing = client.get_annotations(image_id)
            already_done = any(
                a["annotation_type"] == f"{annotation_type}_bbox" and a["source"].startswith("ai")
                for a in existing
            )
            if already_done:
                print("already annotated (skipped)")
                skipped_count += 1
                continue

            # Run detection
            detections = detect_people(file_path)

            if not detections:
                print("no people found")
                no_detections_count += 1
                continue

            # Store each detection as an annotation
            for det in detections:
                client.create_annotation(
                    image_id=image_id,
                    annotation_type=f"{annotation_type}_bbox",
                    value=json.dumps(det),
                    source=f"ai:{yolo_model.replace('.pt', '')}",
                )

            total_people += len(detections)
            annotated_count += 1
            print(f"{len(detections)} person(s)")

        except Exception as e:
            print(f"ERROR: {e}")
            error_count += 1

    return {
        "annotated": annotated_count,
        "skipped": skipped_count,
        "no_detections": no_detections_count,
        "errors": error_count,
        "total_people": total_people,
    }


def main():
    parser = argparse.ArgumentParser(description="ImSor Auto Annotator")
    parser.add_argument("path", help="Image file, folder, or server name to process")
    parser.add_argument(
        "--type", default="person", choices=["person"],
        help="Type of annotation to run (default: person)"
    )
    parser.add_argument(
        "--host", default=platform.node(),
        help="Hostname hint for display (default: computer name)"
    )
    parser.add_argument(
        "--env", choices=["dev", "prod"], default="dev",
        help="Target environment (default: dev)"
    )
    args = parser.parse_args()
    server_url = server_urls[args.env]

    path = args.path
    annotation_type = args.type

    # Determine paths to process
    if os.path.isfile(path):
        folders = [path]
    elif _is_bare_server(path):
        print(f"Detected server name: {path}")
        print("Enumerating network shares...")
        folders = _enumerate_shares(path)
        if not folders:
            print("ERROR: No accessible disk shares found on this server.")
            sys.exit(1)
        print(f"  Found {len(folders)} share(s): {', '.join(folders)}")
        print()
    else:
        if not os.path.isdir(path):
            print(f"ERROR: '{path}' is not a valid file, directory, or server name.")
            sys.exit(1)
        folders = [path]

    print(f"ImSor Auto Annotator")
    print(f"  Environment: {args.env} ({server_url})")
    print(f"  Path:       {path}")
    print(f"  Type:       {annotation_type}")
    print(f"  Target(s):  {len(folders)}")
    print()

    # Authenticate
    print("Logging in to central service...")
    client = ApiClient(server_url)
    try:
        client.login()
    except Exception as e:
        print(f"ERROR: Failed to log in: {e}")
        sys.exit(1)
    print("  OK\n")
    print("  Controls: P = pause/resume, Q = stop gracefully, Ctrl+C = stop after current file\n")

    # Process each path
    totals = {"annotated": 0, "skipped": 0, "no_detections": 0, "errors": 0, "total_people": 0}
    for i, folder in enumerate(folders, 1):
        if _stop_requested:
            break
        if len(folders) > 1:
            print(f"=== Share {i}/{len(folders)}: {folder} ===")
        if not os.path.isfile(folder) and not os.path.isdir(folder):
            print(f"  Skipping (not accessible)\n")
            continue
        counts = _annotate_folder(folder, annotation_type, client)
        for key in totals:
            totals[key] += counts[key]
        print()

    # Summary
    print(f"--- Summary {'(stopped early) ' if _stop_requested else ''}---")
    print(f"  Images annotated:  {totals['annotated']}")
    print(f"  Skipped:           {totals['skipped']}")
    print(f"  No detections:     {totals['no_detections']}")
    print(f"  Errors:            {totals['errors']}")
    print(f"  Total people found: {totals['total_people']}")


if __name__ == "__main__":
    main()
