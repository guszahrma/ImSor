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

    def get_image_by_path(self, file_path: str) -> dict | None:
        """Look up an image record by its file path. Returns None if not found."""
        resp = self._request(
            "GET",
            f"{self.base_url}/images/",
            params={"file_path": file_path, "limit": 1},
        )
        results = resp.json()
        return results[0] if results else None

    def create_annotation(self, image_id: int, annotation_type: str, value: str, source: str = "ai") -> dict:
        resp = self._request(
            "POST",
            f"{self.base_url}/annotations/",
            json={
                "image_id": image_id,
                "annotation_type": annotation_type,
                "value": value,
                "source": source,
            },
        )
        return resp.json()

    def get_annotations(self, image_id: int) -> list[dict]:
        resp = self._request(
            "GET",
            f"{self.base_url}/annotations/",
            params={"image_id": image_id},
        )
        return resp.json()
