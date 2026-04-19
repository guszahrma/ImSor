import requests

import config


_token: str | None = None


def _get_token() -> str:
    global _token
    if _token is None:
        resp = requests.post(
            f"{config.server_url}/auth/login",
            data={"username": config.username, "password": config.password},
        )
        resp.raise_for_status()
        _token = resp.json()["access_token"]
    return _token


def _headers() -> dict:
    return {"Authorization": f"Bearer {_get_token()}"}


def get_unresolved_pairs() -> list[dict]:
    resp = requests.get(
        f"{config.server_url}/duplicates/",
        headers=_headers(),
    )
    resp.raise_for_status()
    return resp.json()


def get_image(image_id: int) -> dict:
    resp = requests.get(
        f"{config.server_url}/images/{image_id}",
        headers=_headers(),
    )
    resp.raise_for_status()
    return resp.json()
