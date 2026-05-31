# Scanner Agent configuration

from credentials import central_service_username as username, central_service_password as password

# Central Web Service URLs per environment
server_urls = {
    "dev":  "http://localhost:8000",
    "prod": "http://localhost:8001",
}

# Checksum algorithm: "sha256", "md5", or "sha1"
checksum_algorithm = "sha256"

# Supported image file extensions (case-insensitive)
image_extensions = [
    ".jpg", ".jpeg", ".png", ".tiff", ".tif",
    ".bmp", ".gif", ".webp", ".heic", ".heif",
    ".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2", ".raf",
]
