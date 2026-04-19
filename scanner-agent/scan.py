import argparse
import platform
import sys

from api_client import ApiClient
from scanner import find_images, build_image_data


def main():
    parser = argparse.ArgumentParser(description="ImSor Scanner Agent")
    parser.add_argument("folder", help="Path to the folder to scan (recursive)")
    parser.add_argument("--host", default=platform.node(), help="Hostname to identify this scanner (default: computer name)")
    args = parser.parse_args()

    folder = args.folder
    scanner_host = args.host

    print(f"ImSor Scanner Agent")
    print(f"  Folder: {folder}")
    print(f"  Host:   {scanner_host}")
    print()

    # 1. Authenticate
    print("Logging in to central service...")
    client = ApiClient()
    try:
        client.login()
    except Exception as e:
        print(f"ERROR: Failed to log in: {e}")
        sys.exit(1)
    print("  OK")

    # 2. Get already-registered images for this host
    print("Fetching registered images for this host...")
    registered = client.get_registered_images(scanner_host)
    registered_by_path = {img["file_path"]: img for img in registered}
    print(f"  {len(registered)} images already registered")

    # 3. Scan local folder
    print(f"Scanning {folder} for images...")
    local_files = find_images(folder)
    print(f"  {len(local_files)} image files found")

    # 4. Compare and sync
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
        print(f"  [{i}/{len(local_files)}] {file_path} ... ", end="", flush=True)
        try:
            image_data = build_image_data(file_path, scanner_host)

            if file_path in registered_by_path:
                existing = registered_by_path[file_path]
                # Check if file has changed (different size or checksum)
                if existing["checksum"] == image_data["checksum"] and existing["file_size"] == image_data["file_size"]:
                    print("unchanged")
                    unchanged_count += 1
                    # Still track checksum for duplicate detection
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

    # 5. Detect files that were deleted locally but still registered
    local_set = set(local_files)
    missing = [path for path in registered_by_path if path.startswith(folder) and path not in local_set]
    if missing:
        print(f"\nNote: {len(missing)} previously registered files no longer exist locally:")
        for path in missing:
            print(f"  - {path}")

    # 6. Report duplicate candidates
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

    # 7. Summary
    print(f"\n--- Summary ---")
    print(f"  New:       {new_count}")
    print(f"  Updated:   {updated_count}")
    print(f"  Unchanged: {unchanged_count}")
    print(f"  Errors:    {error_count}")
    print(f"  Missing:   {len(missing)}")
    print(f"  Duplicate pairs found: {dup_count}")


if __name__ == "__main__":
    main()
