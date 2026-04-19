# Scanner Agent configuration

# Central Web Service URL
server_url = "http://localhost:8000"

# Credentials for authenticating with the central service (must have "user" or "admin" role)
username = "admin"
password = "secret"

# Checksum algorithm: "sha256", "md5", or "sha1"
checksum_algorithm = "sha256"

# Supported image file extensions (case-insensitive)
image_extensions = [
    ".jpg", ".jpeg", ".png", ".tiff", ".tif",
    ".bmp", ".gif", ".webp", ".heic", ".heif",
    ".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2", ".raf",
]
