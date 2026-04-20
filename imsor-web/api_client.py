def get_user_by_username(username: str) -> dict | None:
    """Fetch a user by username (email) from the central service. Returns None if not found."""
    try:
        return _request("GET", f"{config.server_url}/users/by-username/{username}").json()
    except Exception:
        return None
def create_user_via_oauth(username: str, display_name: str | None = None, role: str = "user") -> dict:
    """Create a user in the central service via REST API (for Google OAuth). Password is not set."""
    payload = {
        "username": username,
        "display_name": display_name,
        "password": "oauth_placeholder",  # Not used, but required by schema
        "role": role,
    }
    return _request("POST", f"{config.server_url}/users/", json=payload).json()
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


def get_unresolved_pairs() -> list[dict]:
    return _request("GET", f"{config.server_url}/duplicates/").json()


def get_image(image_id: int) -> dict:
    return _request("GET", f"{config.server_url}/images/{image_id}").json()


def get_annotations(image_id: int) -> list[dict]:
    return _request("GET", f"{config.server_url}/annotations/",
                     params={"image_id": image_id}).json()


def get_all_annotations() -> list[dict]:
    return _request("GET", f"{config.server_url}/annotations/").json()


def get_all_users() -> list[dict]:
    return _request("GET", f"{config.server_url}/users/").json()


def update_annotation(annotation_id: int, value: str) -> dict:
    return _request("PATCH", f"{config.server_url}/annotations/{annotation_id}",
                     json={"value": value}).json()
