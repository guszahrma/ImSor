# Auto Annotator

Detects people in images using a local YOLO model and stores bounding box
annotations in the [Central Web Service](../readme.md#developer-setup) database.
Images must first be registered via the [scanner-agent](../scanner-agent/).

## Prerequisites

1. Install Python 3.10 or newer from <https://www.python.org/downloads/>
   - During installation, check **Add Python to PATH**.
2. Open a PowerShell terminal and navigate to the auto-annotator folder:
   ```
   cd auto-annotator
   ```
3. Create and activate a virtual environment:
   ```
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
   You should see `(venv)` appear at the start of your prompt.
4. Install dependencies:
   ```
   python -m pip install -r requirements.txt
   ```
   This will download the YOLO model weights automatically on first run (~6 MB for yolov8n).

> **Note:** Each time you open a new terminal to run the annotator, activate the virtual environment first with `.\venv\Scripts\Activate.ps1`.

## Configuration

Edit [`config.py`](config.py) before running:

| Setting                | Description                                           | Default                 |
|------------------------|-------------------------------------------------------|-------------------------|
| `server_url`           | URL of the Central Web Service                        | `http://localhost:8000` |
| `username`/`password`  | Credentials for an account with `user` or `admin` role | —                      |
| `yolo_model`           | YOLO model file (larger = more accurate, slower)      | `yolov8n.pt`           |
| `confidence_threshold` | Minimum confidence to accept a detection (0.0–1.0)    | `0.5`                  |
| `image_extensions`     | List of file extensions to process                    | see config.py          |

### YOLO model sizes

| Model         | Speed   | Accuracy | Size   |
|---------------|---------|----------|--------|
| `yolov8n.pt`  | Fastest | Good     | ~6 MB  |
| `yolov8s.pt`  | Fast    | Better   | ~22 MB |
| `yolov8m.pt`  | Medium  | Best     | ~50 MB |

## Usage

**Single image:**
```
python annotate.py "C:\path\to\photo.jpg"
```

**Folder (recursive):**
```
python annotate.py "C:\path\to\photos"
```

**Network share:**
```
python annotate.py "\\server\ShareName\Photos"
```

**Server (all shares):**
```
python annotate.py "\\server"
```

### Options

| Flag            | Description                         | Default         |
|-----------------|-------------------------------------|-----------------|
| `--env dev\|prod` | Target environment                | `dev`           |
| `--type`        | Annotation type to run              | `person`        |
| `--host`        | Hostname hint for display           | computer name   |

### Controls during execution

| Key       | Action                                           |
|-----------|--------------------------------------------------|
| **P**     | Pause / resume                                   |
| **Q**     | Graceful quit — finishes current file, shows summary |
| **Ctrl+C** | Same as Q; press twice to force quit           |

## How it works

1. Finds all image files in the given path.
2. For each image, looks it up in the Central Web Service by file path.
3. Skips images that are not registered or already have AI person annotations.
4. Runs the YOLO model to detect people.
5. Stores each detection as an annotation with:
   - `annotation_type`: `person_bbox`
   - `value`: JSON with `x`, `y`, `width`, `height` (pixels) and `confidence`
   - `source`: `ai`

## Important

Images must be registered with the scanner-agent before running the annotator.
Unregistered images are skipped with a "not registered" message.
