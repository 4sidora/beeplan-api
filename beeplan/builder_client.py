"""HTTP client for beeplan-builder."""

from __future__ import annotations

import httpx

from beeplan.config import get_settings


class BuilderClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.builder_url.rstrip("/")
        self.secret = settings.builder_secret

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.secret}"}

    def start_build(self, payload: dict) -> dict:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{self.base_url}/v1/builds",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    def get_build(self, build_id: str) -> dict:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                f"{self.base_url}/v1/builds/{build_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    def fetch_artifact(self, build_id: str, artifact_name: str) -> bytes:
        with httpx.Client(timeout=120.0) as client:
            resp = client.get(
                f"{self.base_url}/v1/builds/{build_id}/{artifact_name}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.content

    def stream_artifact(self, build_id: str, artifact_name: str):
        """Stream artifact bytes from builder (keeps API worker memory low)."""
        client = httpx.Client(timeout=120.0)
        resp = client.send(
            client.build_request(
                "GET",
                f"{self.base_url}/v1/builds/{build_id}/{artifact_name}",
                headers=self._headers(),
            ),
            stream=True,
        )
        resp.raise_for_status()

        def generate():
            try:
                for chunk in resp.iter_bytes(64 * 1024):
                    if chunk:
                        yield chunk
            finally:
                resp.close()
                client.close()

        return generate

    def fetch_firmware(self, build_id: str) -> bytes:
        return self.fetch_artifact(build_id, "firmware.bin")

    def fetch_manifest(self, build_id: str) -> bytes:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                f"{self.base_url}/v1/builds/{build_id}/manifest.json",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.content

    def get_releases(self) -> dict[str, str]:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{self.base_url}/v1/releases")
            resp.raise_for_status()
            return resp.json()
