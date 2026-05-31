# Auto Annotator configuration

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from credentials import central_service_username as username, central_service_password as password

# Central Web Service URLs per environment
server_urls = {
    "dev":  "http://localhost:8000",
    "prod": "http://localhost:8001",
}

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
