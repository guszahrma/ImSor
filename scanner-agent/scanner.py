import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from imsor_utils import extract_exif, normalize_path  # noqa: E402

from config import checksum_algorithm, image_extensions


def compute_checksum(file_path: str) -> str:
    h = hashlib.new(checksum_algorithm)
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def find_images(folder: str) -> list[str]:
    ext_set = {ext.lower() for ext in image_extensions}
    found = []
    for root, _dirs, files in os.walk(folder):
        for name in files:
            if os.path.splitext(name)[1].lower() in ext_set:
                found.append(os.path.join(root, name))
    return found


def build_image_data(file_path: str, scanner_host: str) -> dict:
    stat = os.stat(file_path)
    exif = extract_exif(file_path)
    return {
        "file_path": normalize_path(file_path),
        "file_name": os.path.basename(file_path),
        "file_size": stat.st_size,
        "checksum": compute_checksum(file_path),
        "scanner_host": scanner_host,
        "date_taken": exif["date_taken"],
        "gps_latitude": exif["gps_latitude"],
        "gps_longitude": exif["gps_longitude"],
        "camera_make": exif["camera_make"],
        "camera_model": exif["camera_model"],
        "image_width": exif["image_width"],
        "image_height": exif["image_height"],
        "exif_orientation": exif["exif_orientation"],
    }
