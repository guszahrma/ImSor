# Scanner Agent

A Python script that runs on a Windows machine. It scans a specified folder
(and subfolders) for images, extracts metadata and checksums, and sends the
results to the [Central Web Service](../readme.md#developer-setup). Running it
again on the same folder will detect changes (new, modified, or deleted files).

## Prerequisites

1. Install Python 3.10 or newer from <https://www.python.org/downloads/>
   - During installation, check **Add Python to PATH**.
2. Open a PowerShell terminal and navigate to the scanner-agent folder:
   ```
   cd scanner-agent
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

> **Note:** Each time you open a new terminal to run the scanner, activate the virtual environment first with `.\venv\Scripts\Activate.ps1`.

## Configuration

Edit [`config.py`](config.py) before running:

| Setting              | Description                                             | Default                  |
|----------------------|---------------------------------------------------------|--------------------------|
| `server_urls`        | URLs of the Central Web Service per environment         | dev: 8000, prod: 8001    |
| `username`/`password`| Credentials for an account with `user` or `admin` role  | —                        |
| `checksum_algorithm` | Hash algorithm for duplicate detection                  | `sha256`                 |
| `image_extensions`   | List of file extensions to scan for                     | see config.py            |

## Running a scan

```
python scan.py "C:\path\to\your\photos"
```

By default the scanner reports to the **dev** environment. Use `--env prod` to target production:

```
python scan.py "C:\path\to\your\photos" --env prod
```

The scanner will:

1. Log in to the central service.
2. Fetch the list of already-registered images for this computer.
3. Recursively scan the folder for image files.
4. For each image: compute checksum, read EXIF data, register or update it.
5. Report if any previously registered files have been deleted locally.
6. Create duplicate candidate pairs for images with matching checksums.

Optional flags:

| Flag | Description | Default |
|------|-------------|---------|
| `--env dev\|prod` | Target environment | `dev` |
| `--host <name>` | Hostname to identify this scanner | your computer name |

Example:
```
python scan.py "C:\Photos" --env prod --host my-desktop
```

## Supported image formats

JPG, JPEG, PNG, TIFF, BMP, GIF, WebP, HEIC, HEIF,
and RAW formats: CR2, CR3, NEF, ARW, DNG, ORF, RW2, RAF.
