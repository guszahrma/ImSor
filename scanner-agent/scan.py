import argparse
import msvcrt
import os
import platform
import re
import signal
import subprocess
import sys

from api_client import ApiClient
from scanner import find_images, build_image_data


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
    """Return True if path is a bare server name like \\\\server or \\\\server\\."""
    return bool(re.match(r'^\\\\[^\\]+\\?$', path))


def _enumerate_shares(server: str) -> list[str]:
    """Use 'net view' to list non-hidden shares on a server. Returns UNC paths."""
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
            # First column is the share name, separated by spaces
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "Disk":
                share_name = parts[0]
                if not share_name.endswith("$"):
                    shares.append(f"{server}\\{share_name}")

    return shares


def _validate_folder(folder: str) -> None:
    """Check that a folder path is accessible."""
    if not os.path.isdir(folder):
        print(f"ERROR: '{folder}' is not a valid directory or is not accessible.")
        sys.exit(1)


def _scan_folder(folder: str, scanner_host: str, client: ApiClient) -> dict:
    """Scan a single folder and return summary counts."""
    # Get already-registered images for this host
    print(f"Fetching registered images for this host...")
    registered = client.get_registered_images(scanner_host)
    registered_by_path = {img["file_path"]: img for img in registered}
    print(f"  {len(registered)} images already registered")

    # Scan folder
    print(f"Scanning {folder} for images...")
    local_files = find_images(folder)
    print(f"  {len(local_files)} image files found")

    # Compare and sync
    new_count = 0
    updated_count = 0
    unchanged_count = 0
    error_count = 0
    all_checksums = {}  # checksum -> list of image IDs (for duplicate detection)

    # Collect existing checksums
    for img in registered:
        if img["checksum"]:
            all_checksums.setdefault(img["checksum"], []).append(img["id"])

    for i, file_path in enumerate(local_files, 1):
        _check_keyboard()
        if _stop_requested:
            print(f"\n  Stopped at file {i}/{len(local_files)}.")
            break

        print(f"  [{i}/{len(local_files)}] {file_path} ... ", end="", flush=True)
        try:
            image_data = build_image_data(file_path, scanner_host)

            if file_path in registered_by_path:
                existing = registered_by_path[file_path]
                # Check if file has changed (different size or checksum)
                if existing["checksum"] == image_data["checksum"] and existing["file_size"] == image_data["file_size"]:
                    print("unchanged")
                    unchanged_count += 1
                    all_checksums.setdefault(image_data["checksum"], [])
                    if existing["id"] not in all_checksums[image_data["checksum"]]:
                        all_checksums[image_data["checksum"]].append(existing["id"])
                else:
                    result = client.update_image(existing["id"], image_data)
                    print("updated")
                    updated_count += 1
                    all_checksums.setdefault(image_data["checksum"], [])
                    if result["id"] not in all_checksums[image_data["checksum"]]:
                        all_checksums[image_data["checksum"]].append(result["id"])
            else:
                result = client.register_image(image_data)
                print("new")
                new_count += 1
                all_checksums.setdefault(image_data["checksum"], [])
                if result["id"] not in all_checksums[image_data["checksum"]]:
                    all_checksums[image_data["checksum"]].append(result["id"])
        except Exception as e:
            print(f"ERROR: {e}")
            error_count += 1

    # Detect files that were deleted locally but still registered
    local_set = set(local_files)
    missing = [path for path in registered_by_path if path.startswith(folder) and path not in local_set]
    if missing:
        print(f"\nNote: {len(missing)} previously registered files no longer exist locally:")
        for path in missing:
            print(f"  - {path}")

    # Report duplicate candidates
    print("\nChecking for duplicate candidates...")
    dup_count = 0
    for checksum, ids in all_checksums.items():
        if len(ids) > 1:
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    try:
                        client.create_duplicate_pair(ids[i], ids[j])
                        dup_count += 1
                    except Exception:
                        pass  # Pair might already exist

    return {
        "new": new_count,
        "updated": updated_count,
        "unchanged": unchanged_count,
        "errors": error_count,
        "missing": len(missing),
        "duplicates": dup_count,
    }


def main():
    parser = argparse.ArgumentParser(description="ImSor Scanner Agent")
    parser.add_argument("folder", help="Path to the folder to scan (recursive)")
    parser.add_argument("--host", default=platform.node(), help="Hostname to identify this scanner (default: computer name)")
    args = parser.parse_args()

    folder = args.folder
    scanner_host = args.host

    # Determine folders to scan
    if _is_bare_server(folder):
        print(f"Detected server name: {folder}")
        print("Enumerating network shares...")
        folders = _enumerate_shares(folder)
        if not folders:
            print("ERROR: No accessible disk shares found on this server.")
            sys.exit(1)
        print(f"  Found {len(folders)} share(s): {', '.join(folders)}")
        print()
    else:
        _validate_folder(folder)
        folders = [folder]

    print(f"ImSor Scanner Agent")
    print(f"  Target:  {folder}")
    print(f"  Host:    {scanner_host}")
    print(f"  Folders: {len(folders)}")
    print()

    # Authenticate
    print("Logging in to central service...")
    client = ApiClient()
    try:
        client.login()
    except Exception as e:
        print(f"ERROR: Failed to log in: {e}")
        sys.exit(1)
    print("  OK\n")
    print("  Controls: P = pause/resume, Q = stop gracefully, Ctrl+C = stop after current file\n")

    # Scan each folder
    totals = {"new": 0, "updated": 0, "unchanged": 0, "errors": 0, "missing": 0, "duplicates": 0}
    for i, scan_folder in enumerate(folders, 1):
        if _stop_requested:
            break
        if len(folders) > 1:
            print(f"=== Share {i}/{len(folders)}: {scan_folder} ===")
        if not os.path.isdir(scan_folder):
            print(f"  Skipping (not accessible)\n")
            continue
        counts = _scan_folder(scan_folder, scanner_host, client)
        for key in totals:
            totals[key] += counts[key]
        print()

    # Summary
    print(f"--- Summary {'(stopped early) ' if _stop_requested else ''}---")
    print(f"  New:       {totals['new']}")
    print(f"  Updated:   {totals['updated']}")
    print(f"  Unchanged: {totals['unchanged']}")
    print(f"  Errors:    {totals['errors']}")
    print(f"  Missing:   {totals['missing']}")
    print(f"  Duplicate pairs found: {totals['duplicates']}")


if __name__ == "__main__":
    main()
