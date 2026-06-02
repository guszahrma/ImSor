"""
One-time repair script: clamp person_bbox coordinates to image bounds.
Run inside the Docker container:
    docker exec imsor-dev-web python /app/clamp_bboxes.py
"""
import json
import sys
sys.path.insert(0, '/app')

from app.database import engine
from app.models import Annotation, Image
from sqlalchemy.orm import Session


def clamp(val, img_w, img_h):
    x = max(0, min(val["x"], img_w - 1))
    y = max(0, min(val["y"], img_h - 1))
    w = min(val["width"],  img_w - x)
    h = min(val["height"], img_h - y)
    return x, y, w, h


with Session(engine) as db:
    rows = (
        db.query(Annotation, Image)
        .join(Image, Annotation.image_id == Image.id)
        .filter(
            Annotation.annotation_type == "person_bbox",
            Image.image_width.isnot(None),
            Image.image_height.isnot(None),
        )
        .all()
    )

    fixed = 0
    skipped = 0
    for ann, img in rows:
        try:
            val = json.loads(ann.value)
        except (json.JSONDecodeError, TypeError):
            skipped += 1
            continue

        x, y, w, h = clamp(val, img.image_width, img.image_height)

        if w <= 0 or h <= 0:
            print(f"  SKIP degenerate ann {ann.id} (would collapse to zero size)")
            skipped += 1
            continue

        if x == val["x"] and y == val["y"] and w == val["width"] and h == val["height"]:
            continue

        print(f"  ann {ann.id} image {img.id}: "
              f"({val['x']},{val['y']} {val['width']}x{val['height']}) -> "
              f"({x},{y} {w}x{h})")
        val["x"] = x
        val["y"] = y
        val["width"]  = w
        val["height"] = h
        ann.value = json.dumps(val)
        fixed += 1

    if fixed:
        db.commit()

print(f"\nDone. Fixed: {fixed}  Skipped: {skipped}  Checked: {len(rows)}")
