import hashlib
import os
from datetime import datetime
from pathlib import PurePosixPath, PureWindowsPath

from PIL import Image
from PIL.ExifTags import Base as ExifBase

from config import checksum_algorithm, image_extensions


def normalize_path(path: str) -> str:
    """Normalize a Windows path to forward-slash UNC format for cross-platform storage.
    e.g. \\\\server\\share\\folder\\file.jpg -> //server/share/folder/file.jpg
    """
    return str(PureWindowsPath(path)).replace("\\", "/")


def compute_checksum(file_path: str) -> str:
    h = hashlib.new(checksum_algorithm)
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def _clean_str(value) -> str | None:
    """Strip NUL bytes and whitespace from EXIF string values."""
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value.replace("\x00", "").strip() or None


_EXIF_ORIENTATION_TO_DEGREES = {1: 0, 3: 180, 6: 90, 8: 270}


def extract_exif(file_path: str) -> dict:
    result = {
        "date_taken": None,
        "gps_latitude": None,
        "gps_longitude": None,
        "camera_make": None,
        "camera_model": None,
        "image_width": None,
        "image_height": None,
        "exif_orientation": 0,
    }
    try:
        with Image.open(file_path) as img:
            result["image_width"] = img.width
            result["image_height"] = img.height

            exif_data = img.getexif()
            if not exif_data:
                return result

            # Date taken
            date_str = _clean_str(exif_data.get(ExifBase.DateTimeOriginal) or exif_data.get(ExifBase.DateTime))
            if date_str:
                for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                    try:
                        result["date_taken"] = datetime.strptime(date_str, fmt).isoformat()
                        break
                    except ValueError:
                        continue

            # Camera info
            result["camera_make"] = _clean_str(exif_data.get(ExifBase.Make))
            result["camera_model"] = _clean_str(exif_data.get(ExifBase.Model))

            # Orientation
            result["exif_orientation"] = _EXIF_ORIENTATION_TO_DEGREES.get(
                exif_data.get(ExifBase.Orientation), 0
            )

            # GPS
            gps_info = exif_data.get_ifd(0x8825)  # GPSInfo IFD
            if gps_info:
                result["gps_latitude"] = _convert_gps(
                    gps_info.get(2), gps_info.get(1)  # GPSLatitude, GPSLatitudeRef
                )
                result["gps_longitude"] = _convert_gps(
                    gps_info.get(4), gps_info.get(3)  # GPSLongitude, GPSLongitudeRef
                )
    except Exception:
        pass  # Not all formats support EXIF; that's fine

    return result


def _convert_gps(coords, ref) -> float | None:
    if not coords or not ref:
        return None
    try:
        degrees = float(coords[0])
        minutes = float(coords[1])
        seconds = float(coords[2])
        value = degrees + minutes / 60 + seconds / 3600
        if ref in ("S", "W"):
            value = -value
        return value
    except (TypeError, IndexError, ValueError):
        return None


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
