import hashlib
import json
import mimetypes
import os
import re
import sys
import ssl
import threading
from datetime import datetime
from pathlib import Path, PurePosixPath

# Workaround for Python 3.13 SSL UNEXPECTED_EOF_WHILE_READING bug with Google OAuth
_ssl_ops = (
    getattr(ssl, 'OP_LEGACY_SERVER_CONNECT', 0) |
    getattr(ssl, 'OP_IGNORE_UNEXPECTED_EOF', 0)
)
if _ssl_ops:
    _orig_wrap_socket = ssl.SSLContext.wrap_socket
    def _patched_wrap_socket(self, *args, **kwargs):
        self.options |= _ssl_ops
        return _orig_wrap_socket(self, *args, **kwargs)
    ssl.SSLContext.wrap_socket = _patched_wrap_socket

sys.path.append(str(Path(__file__).parent.parent / "auto-annotator"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))

from flask_dance.consumer import oauth_authorized
from flask import flash
from flask import Flask, jsonify, request, send_file, abort, redirect, url_for, session
from flask_dance.contrib.google import make_google_blueprint, google
import api_client
import config
from imsor_utils import extract_exif

_MAX_UPLOAD_BYTES = 50 * 1024 * 1024

_YOLO_MODEL_PATH = str(Path(__file__).resolve().parent.parent / "auto-annotator" / f"{config.active_bbox_model}.pt")
_YOLO_SOURCE = f"ai:{config.active_bbox_model}"
_YOLO_CONFIDENCE = 0.5
_yolo_model = None
_yolo_lock = threading.Lock()


def _get_yolo():
    global _yolo_model
    with _yolo_lock:
        if _yolo_model is None:
            from ultralytics import YOLO
            _yolo_model = YOLO(_YOLO_MODEL_PATH)
    return _yolo_model


def _annotate_uploaded_image(image_id: int, file_path: str):
    try:
        model = _get_yolo()
        results = model(file_path, verbose=False)
        for result in results:
            img_h, img_w = result.orig_shape
            for box in result.boxes:
                if int(box.cls[0]) != 0:
                    continue
                conf = float(box.conf[0])
                if conf < _YOLO_CONFIDENCE:
                    continue
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                x1 = max(0, min(round(x1), img_w))
                y1 = max(0, min(round(y1), img_h))
                x2 = max(0, min(round(x2), img_w))
                y2 = max(0, min(round(y2), img_h))
                if x2 <= x1 or y2 <= y1:
                    continue
                api_client.create_annotation(
                    image_id=image_id,
                    user_id=None,
                    annotation_type="person_bbox",
                    value=json.dumps({
                        "x": x1, "y": y1,
                        "width": x2 - x1, "height": y2 - y1,
                        "confidence": round(conf, 4),
                    }),
                    source=_YOLO_SOURCE,
                )
    except Exception as e:
        print(f"[auto-annotator] image {image_id}: {e}")


def resolve_path(stored_path: str) -> str:
    """Convert a stored forward-slash UNC path to a local filesystem path
    using the mappings defined in config.path_mappings."""
    p = PurePosixPath(stored_path)
    for prefix, local_mount in config.path_mappings.items():
        try:
            relative = p.relative_to(PurePosixPath(prefix))
            return str(Path(local_mount) / relative)
        except ValueError:
            continue
    return stored_path  # fallback: return as-is

app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("IMSOR_SECRET_KEY", "imsor_dev_secret")
app.config['SERVER_NAME'] = config.server_name
app.config['PREFERRED_URL_SCHEME'] = 'https'
@app.route("/api/current_user")
def api_current_user():
    user = session.get("user")
    print("[DEBUG] /api/current_user session user:", user)
    if user:
        return jsonify({"logged_in": True, "user": user})
    else:
        return jsonify({"logged_in": False, "user": None}), 200


# Google OAuth setup
google_bp = make_google_blueprint(
    client_id=config.google_client_id,
    client_secret=config.google_client_secret,
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

    # Register user in central-service if not exists, and always fetch user record
    email = user_info.get("email")
    user_record = None
    if email:
        user_record = api_client.get_user_by_username(email)
        if not user_record:
            try:
                api_client.create_user_via_oauth(
                    username=email,
                    display_name=user_info.get("name"),
                    role="unwelcomed",
                )
                user_record = api_client.get_user_by_username(email)
            except Exception:
                pass
    # Store user info and role in session
    session["user"] = {
        **user_info,
        "role": user_record["role"] if user_record else "basic-user",
        "id": user_record["id"] if user_record else None,
    }
    return False  # Prevent Flask-Dance from saving token to DB




@app.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("google_oauth_token", None)
    return redirect(url_for("index"))


@app.before_request
def block_unwelcomed():
    user = session.get("user")
    if user and user.get("role") == "unwelcomed":
        allowed = ("/pending", "/logout", "/login")
        if not any(request.path.startswith(p) for p in allowed):
            return redirect(url_for("pending"))


@app.route("/pending")
def pending():
    return send_file(Path(__file__).parent / "static" / "pending.html")


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


@app.route("/users")
def users():
    return send_file(Path(__file__).parent / "static" / "users.html")


@app.route("/rate")
def rate_page():
    return send_file(Path(__file__).parent / "static" / "rate.html")


@app.route("/admin")
def admin():
    return send_file(Path(__file__).parent / "static" / "admin.html")


@app.route("/api/admin/image-cameras")
def api_image_cameras():
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    return jsonify(api_client.get_image_cameras())


@app.route("/api/admin/camera-model-settings", methods=["GET"])
def api_get_camera_model_settings():
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    return jsonify(api_client.get_camera_model_settings())


@app.route("/api/admin/camera-model-settings", methods=["PATCH"])
def api_patch_camera_model_settings():
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    body = request.get_json()
    return jsonify(api_client.set_camera_model_setting(
        body["make"], body["model"], body["skip_exif_rotation"]
    ))


@app.route("/api/admin/cameras", methods=["GET"])
def api_get_cameras():
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    return jsonify(api_client.get_cameras())


@app.route("/api/admin/cameras", methods=["POST"])
def api_create_camera():
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    body = request.get_json()
    return jsonify(api_client.create_camera(body["user_id"], body["make"], body["model"]))


@app.route("/api/admin/cameras/<int:camera_id>", methods=["DELETE"])
def api_delete_camera(camera_id):
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    return jsonify(api_client.delete_camera(camera_id))


@app.route("/api/admin/person-names")
def api_person_names():
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    return jsonify(api_client.get_person_names())


@app.route("/api/admin/persons", methods=["GET"])
def api_get_persons():
    user = session.get("user")
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    try:
        return jsonify(api_client.get_persons())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/persons/<int:person_id>", methods=["PATCH"])
def api_patch_person(person_id):
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    body = request.get_json()
    return jsonify(api_client.update_person_birthdate(person_id, body.get("birthdate")))


@app.route("/api/admin/person-links", methods=["GET"])
def api_get_person_links():
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    return jsonify(api_client.get_person_links())


@app.route("/api/admin/person-links", methods=["POST"])
def api_create_person_link():
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    body = request.get_json()
    return jsonify(api_client.create_person_link(body["person_name"], body["user_id"]))


@app.route("/api/admin/person-links/<int:link_id>", methods=["DELETE"])
def api_delete_person_link(link_id):
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    return jsonify(api_client.delete_person_link(link_id))


@app.route("/api/admin/users/<int:user_id>/can-create-community", methods=["PATCH"])
def api_set_can_create_community(user_id):
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    body = request.get_json()
    return jsonify(api_client.set_can_create_community(user_id, body["value"]))


@app.route("/api/communities", methods=["GET"])
def api_get_communities():
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    return jsonify(api_client.get_communities())


@app.route("/api/communities", methods=["POST"])
def api_create_community():
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    body = request.get_json()
    creator_id = user.get("id")  # always the logged-in user
    return jsonify(api_client.create_community(creator_id, body["name"]))


@app.route("/api/communities/<int:community_id>", methods=["DELETE"])
def api_delete_community(community_id):
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    return jsonify(api_client.delete_community(community_id))


@app.route("/api/communities/<int:community_id>/members", methods=["POST"])
def api_add_community_member(community_id):
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    body = request.get_json()
    return jsonify(api_client.add_community_member(community_id, body["user_id"]))


@app.route("/api/communities/<int:community_id>/members/<int:user_id>", methods=["DELETE"])
def api_remove_community_member(community_id, user_id):
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    return jsonify(api_client.remove_community_member(community_id, user_id))


@app.route("/api/communities/<int:community_id>/granters", methods=["POST"])
def api_add_community_granter(community_id):
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    body = request.get_json()
    return jsonify(api_client.add_community_granter(community_id, body["user_id"]))


@app.route("/api/communities/<int:community_id>/granters/<int:user_id>", methods=["DELETE"])
def api_remove_community_granter(community_id, user_id):
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    return jsonify(api_client.remove_community_granter(community_id, user_id))


@app.route("/api/rating-queue")
def api_rating_queue():
    user = session.get("user")
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    user_id = user.get("id")
    if not user_id:
        return jsonify({"error": "user has no id"}), 400
    try:
        return jsonify(api_client.get_rating_queue(user_id))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/clusters")
def api_clusters():
    """Return the Annotation Queue of Duplicate Clusters for the logged-in user."""
    user = session.get("user")
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    user_id = user.get("id")
    if not user_id:
        return jsonify({"error": "user has no id"}), 400
    try:
        clusters = api_client.get_clusters(user_id)
        return jsonify(clusters)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/clusters/vote", methods=["POST"])
def api_submit_cluster_vote():
    """Submit a Cluster Vote for the logged-in user."""
    user = session.get("user")
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    user_id = user.get("id")
    if not user_id:
        return jsonify({"error": "user has no id"}), 400
    body = request.get_json()
    votes = body.get("votes") if body else None
    if not isinstance(votes, list):
        return jsonify({"error": "votes must be a list"}), 400
    try:
        result = api_client.submit_cluster_vote(user_id, votes)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/annotated-images/queue")
def annotated_images_queue():
    """Return the bbox annotation queue ordered by the 5-tier annotation priority."""
    user = session.get("user")
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    try:
        return jsonify(api_client.get_bbox_queue(user_id=user["id"]))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/annotated-images/<int:image_id>")
def annotated_image(image_id: int):
    """Return image metadata + user-aware person_bbox annotations for a single image."""
    user = session.get("user")
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    try:
        return jsonify(api_client.get_bbox_image(image_id, user_id=user["id"]))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/known-people")
def known_people():
    """Return person names ordered by most recently used by the current user."""
    user = session.get("user")
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    try:
        return jsonify(api_client.get_known_people(user_id=user["id"]))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/annotations", methods=["POST"])
def api_create_annotation():
    user = session.get("user")
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    body = request.get_json()
    try:
        result = api_client.create_annotation(
            image_id=body["image_id"],
            user_id=user.get("id"),
            annotation_type=body["annotation_type"],
            value=body["value"],
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(result)


@app.route("/api/annotations/<int:annotation_id>", methods=["DELETE"])
def api_delete_annotation(annotation_id: int):
    user = session.get("user")
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    try:
        result = api_client.delete_annotation(annotation_id)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(result)


@app.route("/api/rotation/<int:image_id>", methods=["PUT"])
def api_set_rotation(image_id: int):
    user = session.get("user")
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    body = request.get_json()
    degrees = body.get("degrees", 0) if body else 0
    try:
        result = api_client.set_rotation(image_id, degrees)
        return jsonify(result or {})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/annotations/<int:annotation_id>", methods=["PATCH"])
def patch_annotation(annotation_id: int):
    """Update an annotation's value."""
    user = session.get("user")
    body = request.get_json()
    if not body or "value" not in body:
        abort(400)
    try:
        result = api_client.update_annotation(
            annotation_id, body["value"],
            user_id=user["id"] if user else None,
        )
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

    file_path = resolve_path(image["file_path"])
    if not os.path.isfile(file_path):
        threading.Thread(target=api_client.record_file_missing, args=(image_id,), daemon=True).start()
        abort(404)

    threading.Thread(target=api_client.record_file_resolved, args=(image_id,), daemon=True).start()
    mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    return send_file(file_path, mimetype=mime_type)



@app.route("/api/users")
def api_users():
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    try:
        users = api_client.get_all_users()
        return jsonify(users)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/users/rating-histogram")
def api_rating_histogram():
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    user_ids = request.args.get("user_ids", "")
    try:
        return jsonify(api_client.get_rating_histogram(user_ids))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/users/<int:user_id>/role", methods=["PATCH"])
def api_update_user_role(user_id):
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json()
    role = data.get("role")
    if role not in ("superuser", "maintainer", "basic-user", "unwelcomed"):
        return jsonify({"error": "invalid role"}), 400
    try:
        updated = api_client.update_user_role(user_id, role)
        return jsonify(updated)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/slideshow")
def slideshow():
    user = session.get("user")
    if not user:
        return redirect(url_for("index"))
    return send_file(Path(__file__).parent / "static" / "slideshow.html")


@app.route("/api/slideshow-queue")
def api_slideshow_queue():
    user = session.get("user")
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    min_rating      = request.args.get("min_rating", 7.0, type=float)
    min_raters      = request.args.get("min_raters", 1, type=int)
    and_person_ids  = request.args.get("and_person_ids", "", type=str)
    or_person_ids   = request.args.get("or_person_ids", "", type=str)
    try:
        queue = api_client.get_slideshow_queue(
            user["id"], min_rating, min_raters, and_person_ids, or_person_ids
        )
        return jsonify(queue)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/upload")
def upload_page():
    user = session.get("user")
    if not user or user.get("role") not in ("superuser", "maintainer"):
        abort(403)
    return send_file(Path(__file__).parent / "static" / "upload.html")


@app.route("/attribution")
def attribution_page():
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        abort(403)
    return send_file(Path(__file__).parent / "static" / "attribution.html")


@app.route("/api/attribution/images")
def api_attribution_images():
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    skip = request.args.get("skip", 0, type=int)
    limit = request.args.get("limit", 100, type=int)
    try:
        return jsonify(api_client.get_unattributed_images(skip=skip, limit=limit))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/attribution/images/<int:image_id>", methods=["PATCH"])
def api_set_image_responsible(image_id):
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    body = request.get_json()
    try:
        return jsonify(api_client.set_image_responsible(image_id, body.get("user_id")))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/upload", methods=["POST"])
def api_upload():
    user = session.get("user")
    if not user or user.get("role") not in ("superuser", "maintainer"):
        return jsonify({"error": "forbidden"}), 403

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "no files provided"}), 400

    safe_username = re.sub(r"[^\w.-]", "_", user.get("email", str(user.get("id", "unknown"))))
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    session_dir = Path(config.upload_root) / safe_username / timestamp
    session_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for file in files:
        original_name = file.filename or ""
        if not original_name:
            continue

        if not original_name.lower().endswith((".jpg", ".jpeg")):
            results.append({"filename": original_name, "status": "rejected", "note": "not a JPEG"})
            continue

        data = file.read()
        if len(data) > _MAX_UPLOAD_BYTES:
            results.append({"filename": original_name, "status": "rejected", "note": "exceeds 50 MB"})
            continue

        safe_name = re.sub(r"[^\w(). -]", "_", Path(original_name).name)
        dest = session_dir / safe_name
        counter = 1
        while dest.exists():
            dest = session_dir / f"{dest.stem}_{counter}{dest.suffix}"
            counter += 1

        checksum = hashlib.sha256(data).hexdigest()
        existing = api_client.find_images_by_checksum(checksum)

        dest.write_bytes(data)
        exif = extract_exif(str(dest))
        camera_make = exif.get("camera_make")
        camera_model = exif.get("camera_model")
        if camera_make and camera_model:
            try:
                settings = api_client.get_camera_model_settings()
                skip = any(
                    s["make"] == camera_make and s["model"] == camera_model
                    and s["skip_exif_rotation"]
                    for s in settings
                )
                if skip:
                    exif["exif_orientation"] = 0
            except Exception:
                pass
        stored_path = f"{config.upload_stored_prefix}/{safe_username}/{timestamp}/{dest.name}"

        try:
            registered = api_client.register_image(
                file_path=stored_path,
                file_name=dest.name,
                file_size=len(data),
                checksum=checksum,
                scanner_host="imsor-web-upload",
                image_responsible_id=user.get("id"),
                **exif,
            )
            for dup in existing:
                try:
                    api_client.create_duplicate_pair(registered["id"], dup["id"])
                except Exception:
                    pass
            threading.Thread(
                target=_annotate_uploaded_image,
                args=(registered["id"], str(dest)),
                daemon=True,
            ).start()
            note = f"duplicate of image #{existing[0]['id']}" if existing else ""
            status = "duplicate" if existing else "uploaded"
            results.append({
                "filename": dest.name,
                "status": status,
                "note": note,
                "image_id": registered["id"],
            })
        except Exception as e:
            dest.unlink(missing_ok=True)
            results.append({"filename": dest.name, "status": "error", "note": str(e)})

    return jsonify({"session": timestamp, "results": results})


def check_mounts():
    unmounted = [path for path in config.path_mappings.values() if not os.path.ismount(path)]
    if unmounted:
        print("[WARNING] Configured mount points are not mounted (images under them will 404):")
        for path in unmounted:
            print(f"  - {path}")
    return unmounted


if __name__ == "__main__":
    print(f"ImSor Web running at https://{config.host}:{config.port}")
    check_mounts()
    # Use HTTPS with self-signed certs for local development
    app.run(host=config.host, port=config.port, debug=False, ssl_context=("cert.pem", "key.pem"))
