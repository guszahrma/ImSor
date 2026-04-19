# EXIF Extractor

A standalone tool that extracts all EXIF metadata from an image file and
writes it to a JSON file. Useful for inspecting what metadata is available
in your photos.

## Setup

1. Create and activate a virtual environment:
   ```
   cd exif-extractor
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

## Usage

```
python exif_extract.py "C:\path\to\photo.jpg"
```

This creates a file called `photo.jpg.exif.json` next to the image.

To specify a custom output path:

```
python exif_extract.py "C:\path\to\photo.jpg" --output result.json
```

## Output Format

The JSON file contains:

| Field          | Description                                           |
|----------------|-------------------------------------------------------|
| `source_file`  | Absolute path to the source image                     |
| `tag_count`    | Number of EXIF tags found                             |
| `tags`         | Array of tag objects (see below)                      |

Each tag object:

| Field                | Description                                        |
|----------------------|----------------------------------------------------|
| `ifd`                | IFD section (`IFD0`, `Exif`, `GPS`, `IFD1`)        |
| `tag_id`             | Hex tag ID (e.g. `0x010F`)                          |
| `tag_id_decimal`     | Decimal tag ID (e.g. `271`)                         |
| `tag_name`           | Human-readable name (e.g. `Make`)                   |
| `raw_value`          | The value as stored in the file                     |
| `interpreted_value`  | Human-friendly interpretation (e.g. GPS as decimal degrees) |
