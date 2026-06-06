from datetime import datetime
from pathlib import PureWindowsPath

from PIL import Image
from PIL.ExifTags import Base as ExifBase


def normalize_path(path: str) -> str:
    """Normalize a Windows UNC path to forward-slash form for database storage.
    e.g. \\\\server\\share\\folder\\file.jpg -> //server/share/folder/file.jpg
    """
    return str(PureWindowsPath(path)).replace("\\", "/")


_EXIF_ORIENTATION_TO_DEGREES = {1: 0, 3: 180, 6: 90, 8: 270}


def extract_exif(file_path: str) -> dict:
    """Extract EXIF metadata from an image file.

    Returns a dict with keys: date_taken, gps_latitude, gps_longitude,
    camera_make, camera_model, image_width, image_height, exif_orientation.
    All values default to None / 0 if not present or unreadable.
    """
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

            date_str = _clean_str(
                exif_data.get(ExifBase.DateTimeOriginal) or exif_data.get(ExifBase.DateTime)
            )
            if date_str:
                for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                    try:
                        result["date_taken"] = datetime.strptime(date_str, fmt).isoformat()
                        break
                    except ValueError:
                        continue

            result["camera_make"] = _clean_str(exif_data.get(ExifBase.Make))
            result["camera_model"] = _clean_str(exif_data.get(ExifBase.Model))
            result["exif_orientation"] = _EXIF_ORIENTATION_TO_DEGREES.get(
                exif_data.get(ExifBase.Orientation), 0
            )

            gps_info = exif_data.get_ifd(0x8825)
            if gps_info:
                result["gps_latitude"] = _convert_gps(gps_info.get(2), gps_info.get(1))
                result["gps_longitude"] = _convert_gps(gps_info.get(4), gps_info.get(3))
    except Exception:
        pass

    return result


def _clean_str(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value.replace("\x00", "").strip() or None


def _convert_gps(coords, ref) -> float | None:
    if not coords or not ref:
        return None
    try:
        value = float(coords[0]) + float(coords[1]) / 60 + float(coords[2]) / 3600
        if ref in ("S", "W"):
            value = -value
        return value
    except (TypeError, IndexError, ValueError):
        return None
