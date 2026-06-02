import json

from ultralytics import YOLO

from config import yolo_model, confidence_threshold

# YOLO class ID 0 = "person"
_PERSON_CLASS_ID = 0

_model = None


def _get_model() -> YOLO:
    global _model
    if _model is None:
        _model = YOLO(yolo_model)
    return _model


def detect_people(image_path: str) -> list[dict]:
    """
    Run YOLO person detection on a single image.
    Returns a list of bounding box dicts, each with:
        x, y, width, height (pixels), confidence (float)
    """
    model = _get_model()
    results = model(image_path, verbose=False)

    detections = []
    for result in results:
        img_h, img_w = result.orig_shape
        for box in result.boxes:
            class_id = int(box.cls[0])
            conf = float(box.conf[0])
            if class_id != _PERSON_CLASS_ID:
                continue
            if conf < confidence_threshold:
                continue

            x1, y1, x2, y2 = box.xyxy[0].tolist()
            x1 = max(0, min(round(x1), img_w))
            y1 = max(0, min(round(y1), img_h))
            x2 = max(0, min(round(x2), img_w))
            y2 = max(0, min(round(y2), img_h))
            if x2 <= x1 or y2 <= y1:
                continue
            detections.append({
                "x": x1,
                "y": y1,
                "width": x2 - x1,
                "height": y2 - y1,
                "confidence": round(conf, 4),
            })

    return detections


def detections_to_json(detections: list[dict]) -> list[str]:
    """Convert each detection dict to a JSON string for storage."""
    return [json.dumps(d) for d in detections]
