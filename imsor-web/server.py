



import json
import mimetypes
import os
from pathlib import Path
from flask_dance.consumer import oauth_authorized
from flask import flash
from flask import Flask, jsonify, request, send_file, abort, redirect, url_for, session
from flask_dance.contrib.google import make_google_blueprint, google
import api_client
import sys

sys.path.append(str(Path(__file__).parent.parent / "auto-annotator"))
import credentials

app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("IMSOR_SECRET_KEY", "imsor_dev_secret")
@app.route("/api/current_user")
def api_current_user():
    user = session.get("user")
    if user:
        return jsonify({"logged_in": True, "user": user})
    else:
        return jsonify({"logged_in": False}), 200


# Google OAuth setup
google_bp = make_google_blueprint(
    client_id=credentials.GOOGLE_CLIENT_ID,
    client_secret=credentials.GOOGLE_CLIENT_SECRET,
    scope=[
        "openid",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/userinfo.email"
    ],
    redirect_to="index",
    reprompt_select_account=True
)
app.register_blueprint(google_bp, url_prefix="/login")

# Store user info in session after successful OAuth
@oauth_authorized.connect_via(google_bp)
def google_logged_in(blueprint, token):
    if not token:
        flash("Failed to log in with Google.", category="error")
        return False
    resp = blueprint.session.get("/oauth2/v2/userinfo")
    if not resp.ok:
        flash("Failed to fetch user info from Google.", category="error")
        return False
    user_info = resp.json()
    session["user"] = user_info
    return False  # Prevent Flask-Dance from saving token to DB




@app.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("google_oauth_token", None)
    return redirect(url_for("index"))


@app.route("/")
def index():
    print("[DEBUG] Session at /:", dict(session))
    return send_file(Path(__file__).parent / "static" / "index.html")


@app.route("/duplicates")
def duplicates():
    return send_file(Path(__file__).parent / "static" / "duplicates.html")


@app.route("/annotations")
def annotations():
    return send_file(Path(__file__).parent / "static" / "annotations.html")


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


@app.route("/api/annotated-images")
def annotated_images():
    """Return images that have person_bbox annotations, with their annotations."""
    all_annotations = api_client.get_all_annotations()

    # Group annotations by image_id, only person_bbox
    by_image: dict[int, list[dict]] = {}
    for ann in all_annotations:
        if ann["annotation_type"] == "person_bbox":
            by_image.setdefault(ann["image_id"], []).append(ann)

    result = []
    for image_id, anns in by_image.items():
        try:
            image = api_client.get_image(image_id)
        except Exception:
            continue
        result.append({"image": image, "annotations": anns})

    return jsonify(result)


@app.route("/api/known-people")
def known_people():
    """Return person names ordered by most recently used (newest first)."""
    all_annotations = api_client.get_all_annotations()
    # Track the latest created_at per name
    latest: dict[str, str] = {}
    for ann in all_annotations:
        if ann["annotation_type"] == "person_bbox":
            try:
                val = json.loads(ann["value"])
                name = val.get("person_name")
                if name:
                    ts = ann.get("created_at", "")
                    if name not in latest or ts > latest[name]:
                        latest[name] = ts
            except (json.JSONDecodeError, TypeError):
                pass
    # Sort by timestamp descending (most recent first)
    names = sorted(latest.keys(), key=lambda n: latest[n], reverse=True)
    return jsonify(names)


@app.route("/api/annotations/<int:annotation_id>", methods=["PATCH"])
def patch_annotation(annotation_id: int):
    """Update an annotation's value."""
    body = request.get_json()
    if not body or "value" not in body:
        abort(400)
    try:
        result = api_client.update_annotation(annotation_id, body["value"])
    except Exception:
        abort(500)
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
    print(f"ImSor Web running at https://{config.host}:{config.port}")
    # Use HTTPS with self-signed certs for local development
    app.run(host=config.host, port=config.port, debug=False, ssl_context=("cert.pem", "key.pem"))
