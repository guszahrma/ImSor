"""
Model evaluation script: run a YOLO model on a random sample of
rated, non-skipped, unannotated images and store results.

Usage:
    python test_model.py [--model yolov8x.pt] [--count 10] [--env dev|prod]

Output:
    - Annotations stored in the DB as person_bbox AI annotations
    - CSV written to test_model_results.csv
"""

import argparse
import csv
import json
import platform
import random
import sys
import time

from api_client import ApiClient
from config import server_urls
from detector import detect_people, detections_to_json


def main():
    parser = argparse.ArgumentParser(description="ImSor Model Evaluation")
    parser.add_argument("--model", default="yolov8x.pt", help="YOLO model file (default: yolov8x.pt)")
    parser.add_argument("--count", type=int, default=10, help="Number of images to test (default: 10)")
    parser.add_argument("--env", choices=["dev", "prod"], default="dev")
    args = parser.parse_args()

    server_url = server_urls[args.env]

    print(f"ImSor Model Evaluation")
    print(f"  Model      : {args.model}")
    print(f"  Sample size: {args.count}")
    print(f"  Environment: {args.env} ({server_url})")
    print()

    # Patch model name before detector loads it
    import config as _config
    _config.yolo_model = args.model
    import detector as _detector
    _detector._model = None  # force reload with new model name

    client = ApiClient(server_url)
    try:
        client.login()
    except Exception as e:
        print(f"ERROR: Failed to log in: {e}")
        sys.exit(1)
    print("Logged in.\n")

    print("Fetching annotations...")
    all_anns = client.get_all_annotations()

    rated_ids      = {a["image_id"] for a in all_anns if a["annotation_type"] == "slideshow_rating"}
    skipped_ids    = {a["image_id"] for a in all_anns if a["annotation_type"] == "skip"}
    annotated_ids  = {a["image_id"] for a in all_anns if a["annotation_type"] == "person_bbox"}

    candidate_ids = list(rated_ids - skipped_ids - annotated_ids)
    print(f"  Rated: {len(rated_ids)}  Skipped: {len(skipped_ids)}  Already annotated: {len(annotated_ids)}")
    print(f"  Eligible candidates: {len(candidate_ids)}")

    if not candidate_ids:
        print("No eligible images found.")
        sys.exit(0)

    sample = random.sample(candidate_ids, min(args.count, len(candidate_ids)))
    print(f"  Sampled: {len(sample)}\n")

    rows = []
    csv_file = f"test_model_results_{args.model.replace('.pt','')}.csv"

    for i, image_id in enumerate(sample, 1):
        try:
            image = client.get_image(image_id)
        except Exception as e:
            print(f"  [{i}/{len(sample)}] id={image_id} ERROR fetching: {e}")
            continue

        file_path = image["file_path"].replace("/", "\\")
        file_name = image["file_name"]
        print(f"  [{i}/{len(sample)}] {file_name} ... ", end="", flush=True)

        try:
            t0 = time.perf_counter()
            detections = detect_people(file_path)
            elapsed = time.perf_counter() - t0
        except Exception as e:
            print(f"ERROR: {e}")
            rows.append({"image_id": image_id, "file_name": file_name,
                         "processing_time_s": "", "people_count": "", "error": str(e)})
            continue

        # Store in DB
        for det in detections:
            try:
                client.create_annotation(
                    image_id=image_id,
                    annotation_type="person_bbox",
                    value=json.dumps(det),
                    source="ai",
                )
            except Exception as e:
                print(f"\n    WARNING: failed to store annotation: {e}")

        print(f"{len(detections)} person(s)  {elapsed:.2f}s")
        rows.append({
            "image_id": image_id,
            "file_name": file_name,
            "processing_time_s": round(elapsed, 3),
            "people_count": len(detections),
            "error": "",
        })

    # Write CSV
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["image_id", "file_name", "processing_time_s", "people_count", "error"])
        writer.writeheader()
        writer.writerows(rows)

        valid = [r for r in rows if r["processing_time_s"] != ""]
        if valid:
            avg_time = sum(r["processing_time_s"] for r in valid) / len(valid)
            total_people = sum(r["people_count"] for r in valid)
            f.write("\n")
            f.write(f"# Summary\n")
            f.write(f"# Model: {args.model}\n")
            f.write(f"# Images processed: {len(valid)}\n")
            f.write(f"# Average processing time: {avg_time:.3f}s\n")
            f.write(f"# Total people found: {total_people}\n")

    print()
    print(f"Done. Results written to {csv_file}")
    if valid:
        avg_time = sum(r["processing_time_s"] for r in valid) / len(valid)
        print(f"  Average processing time : {avg_time:.3f}s")
        print(f"  Total people found      : {sum(r['people_count'] for r in valid)}")


if __name__ == "__main__":
    main()
