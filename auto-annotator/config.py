# Auto Annotator configuration

# Central Web Service URL
server_url = "http://localhost:8000"

# Credentials for authenticating with the central service (must have "user" or "admin" role)
username = "admin"
password = "secret"

# YOLO model to use (downloaded automatically on first run)
# Options: "yolov8n.pt" (fastest), "yolov8s.pt" (balanced), "yolov8m.pt" (more accurate)
yolo_model = "yolov8n.pt"

# Minimum confidence threshold for person detections (0.0 - 1.0)
confidence_threshold = 0.5

# Supported image file extensions (case-insensitive)
image_extensions = [
    ".jpg", ".jpeg", ".png", ".tiff", ".tif",
    ".bmp", ".gif", ".webp", ".heic", ".heif",
    ".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2", ".raf",
]
