import mimetypes
import os
from pathlib import Path

from flask import Flask, jsonify, send_file, abort

import api_client

app = Flask(__name__, static_folder="static")


@app.route("/")
def index():
    return send_file(Path(__file__).parent / "static" / "index.html")


@app.route("/duplicates")
def duplicates():
    return send_file(Path(__file__).parent / "static" / "duplicates.html")


@app.route("/api/pairs")
def pairs():
    """Return unresolved duplicate pairs with image metadata."""
    raw_pairs = api_client.get_unresolved_pairs()
    result = []
    for pair in raw_pairs:
        try:
            image_a = api_client.get_image(pair["image_a_id"])
            image_b = api_client.get_image(pair["image_b_id"])
        except Exception:
            continue
        result.append({
            "id": pair["id"],
            "match_type": pair["match_type"],
            "image_a": image_a,
            "image_b": image_b,
        })
    return jsonify(result)


@app.route("/serve/<int:image_id>")
def serve_image(image_id: int):
    """Serve an image file from the local filesystem by its database ID."""
    try:
        image = api_client.get_image(image_id)
    except Exception:
        abort(404)

    file_path = image["file_path"]
    if not os.path.isfile(file_path):
        abort(404)

    mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    return send_file(file_path, mimetype=mime_type)


if __name__ == "__main__":
    import config

    print(f"ImSor Web running at http://{config.host}:{config.port}")
    app.run(host=config.host, port=config.port, debug=False)
