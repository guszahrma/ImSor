import requests

from config import username, password


class ApiClient:
    def __init__(self, server_url: str):
        self.base_url = server_url.rstrip("/")
        self.token = None

    def login(self):
        resp = requests.post(
            f"{self.base_url}/auth/login",
            data={"username": username, "password": password},
        )
        resp.raise_for_status()
        self.token = resp.json()["access_token"]

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _request(self, method, url, **kwargs):
        """Make a request, automatically re-login on 401."""
        kwargs.setdefault("headers", self._headers())
        resp = requests.request(method, url, **kwargs)
        if resp.status_code == 401:
            self.login()
            kwargs["headers"] = self._headers()
            resp = requests.request(method, url, **kwargs)
        resp.raise_for_status()
        return resp

    def get_registered_images(self, scanner_host: str) -> list[dict]:
        images = []
        skip = 0
        limit = 1000
        while True:
            resp = self._request(
                "GET",
                f"{self.base_url}/images/",
                params={"scanner_host": scanner_host, "skip": skip, "limit": limit},
            )
            batch = resp.json()
            if not batch:
                break
            images.extend(batch)
            if len(batch) < limit:
                break
            skip += limit
        return images

    def register_image(self, image_data: dict) -> dict:
        resp = self._request(
            "POST",
            f"{self.base_url}/images/",
            json=image_data,
        )
        return resp.json()

    def update_image(self, image_id: int, image_data: dict) -> dict:
        resp = self._request(
            "PUT",
            f"{self.base_url}/images/{image_id}",
            json=image_data,
        )
        return resp.json()

    def patch_exif_orientation(self, image_id: int, exif_orientation: int) -> dict:
        resp = self._request(
            "PATCH",
            f"{self.base_url}/images/{image_id}/exif-orientation",
            json={"exif_orientation": exif_orientation},
        )
        return resp.json()

    def create_duplicate_pair(self, image_a_id: int, image_b_id: int) -> dict:
        resp = self._request(
            "POST",
            f"{self.base_url}/duplicates/",
            json={"image_a_id": image_a_id, "image_b_id": image_b_id, "match_type": "checksum"},
        )
        return resp.json()
