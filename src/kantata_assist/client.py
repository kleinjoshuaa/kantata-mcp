"""HTTP client for Kantata OX (Mavenlink) API v1."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import httpx

DEFAULT_API_BASE = "https://api.mavenlink.com/api/v1"


class KantataAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _normalize_results(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Expand Kantata `results` + keyed object maps into a list of merged records."""
    results = payload.get("results") or []
    out: list[dict[str, Any]] = []
    for ref in results:
        if not isinstance(ref, dict):
            continue
        key = ref.get("key")
        rid = ref.get("id")
        if not key or rid is None:
            continue
        bucket = payload.get(key)
        if not isinstance(bucket, dict):
            continue
        obj = bucket.get(str(rid))
        if isinstance(obj, dict):
            row = dict(obj)
            row["_type"] = key
            out.append(row)
    return out


class KantataClient:
    def __init__(
        self,
        access_token: str,
        *,
        api_base: str | None = None,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_base = (api_base or DEFAULT_API_BASE).rstrip("/")
        kwargs: dict[str, Any] = {
            "base_url": self._api_base,
            "headers": {"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            "timeout": timeout,
        }
        if transport is not None:
            kwargs["transport"] = transport
        self._client = httpx.Client(**kwargs)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> KantataClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Any = None,
        data: Any = None,
        files: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        path = path if path.startswith("/") else f"/{path}"
        if not path.endswith(".json"):
            path = f"{path}.json"
        try:
            r = self._client.request(
                method,
                path,
                params=dict(params or {}),
                json=json_body if files is None else None,
                data=data,
                files=files,
                headers=dict(headers) if headers else None,
            )
        except httpx.RequestError as e:
            raise KantataAPIError(f"HTTP request failed: {e}") from e
        text = r.text
        if r.status_code == 204 or not text.strip():
            payload: dict[str, Any] = {}
        elif r.headers.get("content-type", "").startswith("application/json"):
            try:
                raw = r.json()
                payload = raw if isinstance(raw, dict) else {"_raw": raw}
            except json.JSONDecodeError as e:
                raise KantataAPIError(
                    "Invalid JSON response",
                    status_code=r.status_code,
                    body=text[:2000],
                ) from e
        else:
            payload = {}
        if not r.is_success:
            msg = payload.get("errors") if isinstance(payload, dict) else None
            detail = json.dumps(msg or payload)[:2000] if msg or payload else text[:2000]
            raise KantataAPIError(
                f"Kantata API error {r.status_code}: {detail}",
                status_code=r.status_code,
                body=text[:2000],
            )
        if not isinstance(payload, dict):
            return {"_raw": payload}
        return payload

    def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return self.request("DELETE", path, **kwargs)

    @staticmethod
    def items(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
        return _normalize_results(payload)

    @staticmethod
    def first_id(payload: Mapping[str, Any]) -> str | None:
        items = _normalize_results(payload)
        if not items:
            return None
        return str(items[0].get("id", ""))
