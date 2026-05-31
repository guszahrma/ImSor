"""
One-time migration: read EXIF orientation from every registered image file and
update the exif_orientation column in the DB where it differs from the stored value.

Run once after the 003_exif_orientation.sql migration.

Usage:
    python backfill_orientation.py [--host HOSTNAME] [--env dev|prod]
"""

import argparse
import platform
import sys

from api_client import ApiClient
from config import server_urls
from scanner import extract_exif


def main():
    parser = argparse.ArgumentParser(description="Backfill exif_orientation for existing images")
    parser.add_argument("--host", default=platform.node(), help="Scanner host name (default: computer name)")
    parser.add_argument("--env", choices=["dev", "prod"], default="dev", help="Target environment (default: dev)")
    args = parser.parse_args()

    server_url = server_urls[args.env]
    scanner_host = args.host

    print("ImSor — Backfill EXIF Orientation")
    print(f"  Environment : {args.env} ({server_url})")
    print(f"  Scanner host: {scanner_host}")
    print()

    client = ApiClient(server_url)
    try:
        client.login()
    except Exception as e:
        print(f"ERROR: Failed to log in: {e}")
        sys.exit(1)
    print("Logged in.\n")

    print("Fetching registered images...")
    try:
        images = client.get_registered_images(scanner_host)
    except Exception as e:
        print(f"ERROR: Failed to fetch images: {e}")
        sys.exit(1)
    print(f"  {len(images)} images found\n")

    updated = 0
    already_correct = 0
    missing = 0
    errors = 0

    for i, image in enumerate(images, 1):
        image_id = image["id"]
        stored = image.get("exif_orientation") or 0
        file_path = image["file_path"].replace("/", "\\")

        print(f"  [{i}/{len(images)}] {image['file_name']} ... ", end="", flush=True)

        try:
            exif = extract_exif(file_path)
        except FileNotFoundError:
            print(f"MISSING ({file_path})")
            missing += 1
            continue
        except Exception as e:
            print(f"ERROR reading EXIF: {e}")
            errors += 1
            continue

        orientation = exif["exif_orientation"]

        if orientation == stored:
            print("ok")
            already_correct += 1
            continue

        try:
            client.patch_exif_orientation(image_id, orientation)
            print(f"updated {stored}° → {orientation}°")
            updated += 1
        except Exception as e:
            print(f"ERROR patching: {e}")
            errors += 1

    print()
    print("Done.")
    print(f"  Updated       : {updated}")
    print(f"  Already correct: {already_correct}")
    print(f"  Missing files  : {missing}")
    print(f"  Errors         : {errors}")


if __name__ == "__main__":
    main()
