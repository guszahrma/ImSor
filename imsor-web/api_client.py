def get_user_by_username(username: str) -> dict | None:
    """Fetch a user by username (email) from the central service. Returns None if not found."""
    try:
        return _request("GET", f"{config.server_url}/users/by-username/{username}").json()
    except Exception:
        return None
def create_user_via_oauth(username: str, display_name: str | None = None, role: str = "basic-user") -> dict:
    """Create a user in the central service via REST API (for Google OAuth). Password is not set."""
    payload = {
        "username": username,
        "display_name": display_name,
        "password": "oauth_placeholder",  # Not used, but required by schema
        "role": role,
    }
    return _request("POST", f"{config.server_url}/users/", json=payload).json()
def update_user_role(user_id: int, role: str) -> dict:
    """Update a user's role in the central service."""
    return _request("PATCH", f"{config.server_url}/users/{user_id}/role", json={"role": role}).json()
import requests

import config


_token: str | None = None


def _refresh_token():
    global _token
    resp = requests.post(
        f"{config.server_url}/auth/login",
        data={"username": config.username, "password": config.password},
    )
    resp.raise_for_status()
    _token = resp.json()["access_token"]


def _get_token() -> str:
    if _token is None:
        _refresh_token()
    return _token


def _headers() -> dict:
    return {"Authorization": f"Bearer {_get_token()}"}


def _request(method: str, url: str, **kwargs) -> requests.Response:
    """Make a request, automatically re-login on 401."""
    kwargs.setdefault("headers", _headers())
    resp = requests.request(method, url, **kwargs)
    if resp.status_code == 401:
        _refresh_token()
        kwargs["headers"] = _headers()
        resp = requests.request(method, url, **kwargs)
    resp.raise_for_status()
    return resp


def get_clusters(user_id: int) -> list[dict]:
    """Return the Annotation Queue of Duplicate Clusters for the given annotator."""
    return _request("GET", f"{config.server_url}/duplicates/clusters",
                    params={"user_id": user_id}).json()


def submit_cluster_vote(user_id: int, votes: list[dict]) -> list[dict]:
    """Upsert a Cluster Vote. votes: [{"image_id": int, "value": str}, ...]"""
    return _request("POST", f"{config.server_url}/annotations/batch-vote",
                    json={"user_id": user_id, "votes": votes}).json()


def get_image(image_id: int) -> dict:
    return _request("GET", f"{config.server_url}/images/{image_id}").json()


def get_annotations(image_id: int) -> list[dict]:
    return _request("GET", f"{config.server_url}/annotations/",
                     params={"image_id": image_id}).json()


def get_all_annotations() -> list[dict]:
    return _request("GET", f"{config.server_url}/annotations/").json()


def create_annotation(image_id: int, user_id: int | None, annotation_type: str, value: str) -> dict:
    return _request("POST", f"{config.server_url}/annotations/", json={
        "image_id": image_id,
        "user_id": user_id,
        "annotation_type": annotation_type,
        "value": value,
        "source": "manual",
    }).json()


def delete_annotation(annotation_id: int) -> dict:
    return _request("DELETE", f"{config.server_url}/annotations/{annotation_id}").json()


def get_bbox_queue() -> list[dict]:
    """Return the bbox annotation queue: images with at least one unnamed person_bbox."""
    return _request("GET", f"{config.server_url}/annotations/bbox-queue").json()


def get_bbox_image(image_id: int) -> dict:
    """Return image metadata + person_bbox annotations for a single image."""
    return _request("GET", f"{config.server_url}/annotations/bbox-image/{image_id}").json()


def get_all_users() -> list[dict]:
    return _request("GET", f"{config.server_url}/users/").json()


# --- Admin ---

def get_image_cameras() -> list[dict]:
    """Return distinct (make, model) pairs from the image library."""
    return _request("GET", f"{config.server_url}/admin/image-cameras").json()

def get_cameras() -> list[dict]:
    return _request("GET", f"{config.server_url}/admin/cameras").json()

def create_camera(user_id: int, make: str, model: str) -> dict:
    return _request("POST", f"{config.server_url}/admin/cameras",
                    json={"user_id": user_id, "make": make, "model": model}).json()

def delete_camera(camera_id: int) -> dict:
    return _request("DELETE", f"{config.server_url}/admin/cameras/{camera_id}").json()

def get_person_names() -> list[str]:
    return _request("GET", f"{config.server_url}/admin/person-names").json()

def get_person_links() -> list[dict]:
    return _request("GET", f"{config.server_url}/admin/person-links").json()

def create_person_link(person_name: str, user_id: int) -> dict:
    return _request("POST", f"{config.server_url}/admin/person-links",
                    json={"person_name": person_name, "user_id": user_id}).json()

def delete_person_link(link_id: int) -> dict:
    return _request("DELETE", f"{config.server_url}/admin/person-links/{link_id}").json()

def set_can_create_community(user_id: int, value: bool) -> dict:
    return _request("PATCH", f"{config.server_url}/admin/users/{user_id}/can-create-community",
                    json={"value": value}).json()

def get_communities() -> list[dict]:
    return _request("GET", f"{config.server_url}/communities/").json()

def create_community(creator_id: int, name: str) -> dict:
    return _request("POST", f"{config.server_url}/communities/",
                    json={"creator_id": creator_id, "name": name}).json()

def delete_community(community_id: int) -> dict:
    return _request("DELETE", f"{config.server_url}/communities/{community_id}").json()

def add_community_member(community_id: int, user_id: int) -> dict:
    return _request("POST", f"{config.server_url}/communities/{community_id}/members",
                    json={"user_id": user_id}).json()

def remove_community_member(community_id: int, user_id: int) -> dict:
    return _request("DELETE", f"{config.server_url}/communities/{community_id}/members/{user_id}").json()

def add_community_granter(community_id: int, user_id: int) -> dict:
    return _request("POST", f"{config.server_url}/communities/{community_id}/granters",
                    json={"user_id": user_id}).json()

def remove_community_granter(community_id: int, user_id: int) -> dict:
    return _request("DELETE", f"{config.server_url}/communities/{community_id}/granters/{user_id}").json()


def update_annotation(annotation_id: int, value: str) -> dict:
    return _request("PATCH", f"{config.server_url}/annotations/{annotation_id}",
                     json={"value": value}).json()


