import requests

from config import server_url, username, password


class ApiClient:
    def __init__(self):
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

    def get_registered_images(self, scanner_host: str) -> list[dict]:
        images = []
        skip = 0
        limit = 1000
        while True:
            resp = requests.get(
                f"{self.base_url}/images/",
                params={"scanner_host": scanner_host, "skip": skip, "limit": limit},
                headers=self._headers(),
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            images.extend(batch)
            if len(batch) < limit:
                break
            skip += limit
        return images

    def register_image(self, image_data: dict) -> dict:
        resp = requests.post(
            f"{self.base_url}/images/",
            json=image_data,
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def update_image(self, image_id: int, image_data: dict) -> dict:
        resp = requests.put(
            f"{self.base_url}/images/{image_id}",
            json=image_data,
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def create_duplicate_pair(self, image_a_id: int, image_b_id: int) -> dict:
        resp = requests.post(
            f"{self.base_url}/duplicates/",
            json={"image_a_id": image_a_id, "image_b_id": image_b_id, "match_type": "checksum"},
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()
