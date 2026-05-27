import json
import mimetypes
import os
import sys
import ssl
from pathlib import Path

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

import credentials
from flask_dance.consumer import oauth_authorized
from flask import flash
from flask import Flask, jsonify, request, send_file, abort, redirect, url_for, session
from flask_dance.contrib.google import make_google_blueprint, google
import api_client
import config
from pathlib import PurePosixPath, Path


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
                    role="basic-user",
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


@app.route("/admin")
def admin():
    return send_file(Path(__file__).parent / "static" / "admin.html")


@app.route("/api/admin/image-cameras")
def api_image_cameras():
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    return jsonify(api_client.get_image_cameras())


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
    """Return the bbox annotation queue (images with at least one unnamed person_bbox)."""
    user = session.get("user")
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    try:
        return jsonify(api_client.get_bbox_queue())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/annotated-images/<int:image_id>")
def annotated_image(image_id: int):
    """Return image metadata + person_bbox annotations for a single image."""
    user = session.get("user")
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    try:
        return jsonify(api_client.get_bbox_image(image_id))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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

    file_path = resolve_path(image["file_path"])
    if not os.path.isfile(file_path):
        abort(404)

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


@app.route("/api/users/<int:user_id>/role", methods=["PATCH"])
def api_update_user_role(user_id):
    user = session.get("user")
    if not user or user.get("role") != "superuser":
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json()
    role = data.get("role")
    if role not in ("superuser", "maintainer", "basic-user"):
        return jsonify({"error": "invalid role"}), 400
    try:
        updated = api_client.update_user_role(user_id, role)
        return jsonify(updated)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print(f"ImSor Web running at https://{config.host}:{config.port}")
    # Use HTTPS with self-signed certs for local development
    app.run(host=config.host, port=config.port, debug=False, ssl_context=("cert.pem", "key.pem"))
