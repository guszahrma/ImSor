"""
One-time migration: read EXIF orientation from every registered image file and
update the exif_orientation column in the DB where it differs from the stored value.

Run once after the 003_exif_orientation.sql migration.

Usage:
    python backfill_orientation.py [--host HOSTNAME] [--env dev|prod]

Console shows a progress counter. Unexpected outcomes (updated, missing, errors)
are written to backfill_orientation.log in the current directory.
"""

import argparse
import platform
import sys
from datetime import datetime

from api_client import ApiClient
from config import server_urls
from scanner import extract_exif

LOG_FILE = "backfill_orientation.log"


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
    print(f"  Log file    : {LOG_FILE}")
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
    total = len(images)

    with open(LOG_FILE, "w", encoding="utf-8") as log:
        log.write(f"backfill_orientation — {datetime.now().isoformat()}\n")
        log.write(f"host={scanner_host}  env={args.env}  total={total}\n")
        log.write("-" * 60 + "\n")

        for i, image in enumerate(images, 1):
            image_id = image["id"]
            stored = image.get("exif_orientation") or 0
            file_path = image["file_path"].replace("/", "\\")

            print(f"\r  {i}/{total}  (updated={updated} missing={missing} errors={errors})", end="", flush=True)

            try:
                exif = extract_exif(file_path)
            except FileNotFoundError:
                log.write(f"MISSING  id={image_id}  {file_path}\n")
                missing += 1
                continue
            except Exception as e:
                log.write(f"ERROR    id={image_id}  {image['file_name']}  reading EXIF: {e}\n")
                errors += 1
                continue

            orientation = exif["exif_orientation"]

            if orientation == stored:
                already_correct += 1
                continue

            try:
                client.patch_exif_orientation(image_id, orientation)
                log.write(f"UPDATED  id={image_id}  {image['file_name']}  {stored}° → {orientation}°\n")
                updated += 1
            except Exception as e:
                log.write(f"ERROR    id={image_id}  {image['file_name']}  patching: {e}\n")
                errors += 1

        log.write("-" * 60 + "\n")
        log.write(f"updated={updated}  already_correct={already_correct}  missing={missing}  errors={errors}\n")

    print()
    print()
    print("Done.")
    print(f"  Updated        : {updated}")
    print(f"  Already correct: {already_correct}")
    print(f"  Missing files  : {missing}")
    print(f"  Errors         : {errors}")
    print(f"\nSee {LOG_FILE} for details.")


if __name__ == "__main__":
    main()
