"""
EXIF Extractor - Extracts all EXIF tags from an image and writes them to a JSON file.

Usage:
    python exif_extract.py <image_path> [--output <output.json>]

If --output is not specified, the JSON file is written next to the image
with the same name and a .exif.json extension.
"""

import argparse
import json
import os
import sys

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS, IFD


def decode_value(value):
    """Convert EXIF values to JSON-serializable types."""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return value.hex()
    elif isinstance(value, tuple):
        return [decode_value(v) for v in value]
    elif isinstance(value, dict):
        return {str(k): decode_value(v) for k, v in value.items()}
    elif isinstance(value, (int, float, str, bool)):
        return value
    else:
        return str(value)


def interpret_gps_coord(coords, ref):
    """Convert GPS coordinates tuple + ref to decimal degrees string."""
    if not coords or not ref:
        return None
    try:
        degrees = float(coords[0])
        minutes = float(coords[1])
        seconds = float(coords[2])
        value = degrees + minutes / 60 + seconds / 3600
        if ref in ("S", "W"):
            value = -value
        return f"{value:.6f}"
    except (TypeError, IndexError, ValueError):
        return None


def extract_exif(image_path: str) -> list[dict]:
    results = []

    with Image.open(image_path) as img:
        exif_data = img.getexif()
        if not exif_data:
            return results

        # Main IFD tags
        for tag_id, value in exif_data.items():
            tag_name = TAGS.get(tag_id, f"Unknown_0x{tag_id:04X}")
            raw = decode_value(value)
            results.append({
                "ifd": "IFD0",
                "tag_id": f"0x{tag_id:04X}",
                "tag_id_decimal": tag_id,
                "tag_name": tag_name,
                "raw_value": raw,
                "interpreted_value": raw,
            })

        # EXIF sub-IFD
        try:
            exif_ifd = exif_data.get_ifd(IFD.Exif)
            for tag_id, value in exif_ifd.items():
                tag_name = TAGS.get(tag_id, f"Unknown_0x{tag_id:04X}")
                raw = decode_value(value)
                results.append({
                    "ifd": "Exif",
                    "tag_id": f"0x{tag_id:04X}",
                    "tag_id_decimal": tag_id,
                    "tag_name": tag_name,
                    "raw_value": raw,
                    "interpreted_value": raw,
                })
        except Exception:
            pass

        # GPS IFD
        try:
            gps_ifd = exif_data.get_ifd(IFD.GPSInfo)
            lat_ref = None
            lon_ref = None
            lat_coords = None
            lon_coords = None

            for tag_id, value in gps_ifd.items():
                tag_name = GPSTAGS.get(tag_id, f"Unknown_GPS_0x{tag_id:04X}")
                raw = decode_value(value)

                interpreted = raw
                if tag_id == 1:  # GPSLatitudeRef
                    lat_ref = value
                elif tag_id == 2:  # GPSLatitude
                    lat_coords = value
                elif tag_id == 3:  # GPSLongitudeRef
                    lon_ref = value
                elif tag_id == 4:  # GPSLongitude
                    lon_coords = value

                results.append({
                    "ifd": "GPS",
                    "tag_id": f"0x{tag_id:04X}",
                    "tag_id_decimal": tag_id,
                    "tag_name": tag_name,
                    "raw_value": raw,
                    "interpreted_value": interpreted,
                })

            # Add interpreted lat/lon as decimal degrees
            lat_decimal = interpret_gps_coord(lat_coords, lat_ref)
            if lat_decimal:
                for entry in results:
                    if entry["ifd"] == "GPS" and entry["tag_name"] == "GPSLatitude":
                        entry["interpreted_value"] = f"{lat_decimal}° (decimal degrees)"
            lon_decimal = interpret_gps_coord(lon_coords, lon_ref)
            if lon_decimal:
                for entry in results:
                    if entry["ifd"] == "GPS" and entry["tag_name"] == "GPSLongitude":
                        entry["interpreted_value"] = f"{lon_decimal}° (decimal degrees)"
        except Exception:
            pass

        # IFD1 (thumbnail)
        try:
            ifd1 = exif_data.get_ifd(IFD.IFD1)
            for tag_id, value in ifd1.items():
                tag_name = TAGS.get(tag_id, f"Unknown_0x{tag_id:04X}")
                raw = decode_value(value)
                results.append({
                    "ifd": "IFD1",
                    "tag_id": f"0x{tag_id:04X}",
                    "tag_id_decimal": tag_id,
                    "tag_name": tag_name,
                    "raw_value": raw,
                    "interpreted_value": raw,
                })
        except Exception:
            pass

    return results


def main():
    parser = argparse.ArgumentParser(description="Extract all EXIF tags from an image to JSON")
    parser.add_argument("image", help="Path to the image file")
    parser.add_argument("--output", "-o", help="Output JSON file path (default: <image>.exif.json)")
    args = parser.parse_args()

    if not os.path.isfile(args.image):
        print(f"ERROR: File not found: {args.image}")
        sys.exit(1)

    output_path = args.output or (args.image + ".exif.json")

    print(f"Extracting EXIF from: {args.image}")
    tags = extract_exif(args.image)

    output = {
        "source_file": os.path.abspath(args.image),
        "tag_count": len(tags),
        "tags": tags,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"  {len(tags)} tags extracted")
    print(f"  Written to: {output_path}")


if __name__ == "__main__":
    main()
