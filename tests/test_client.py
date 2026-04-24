"""Tests for KantataClient (HTTP behavior via MockTransport)."""

from __future__ import annotations

import httpx
import pytest

from kantata_assist.client import DEFAULT_API_BASE, KantataAPIError, KantataClient


def _client(handler: httpx.MockTransport) -> KantataClient:
    return KantataClient("tok", api_base="https://test.invalid/api/v1", transport=handler)


def test_request_appends_json_suffix() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/foo.json")
        return httpx.Response(200, json={"ok": True})

    c = _client(httpx.MockTransport(handler))
    assert c.get("/foo") == {"ok": True}
    c.close()


def test_request_sends_bearer_and_accept() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") == "Bearer tok"
        assert "application/json" in (request.headers.get("accept") or "")
        return httpx.Response(200, json={})

    c = _client(httpx.MockTransport(handler))
    c.get("/x")
    c.close()


def test_204_returns_empty_dict() -> None:
    c = _client(
        httpx.MockTransport(lambda r: httpx.Response(204)),
    )
    assert c.delete("/stories/1") == {}
    c.close()


def test_empty_body_returns_empty_dict() -> None:
    c = _client(
        httpx.MockTransport(lambda r: httpx.Response(200, text="  \n")),
    )
    assert c.get("/x") == {}
    c.close()


def test_error_response_raises_kantata_api_error() -> None:
    body = {"errors": [{"type": "system", "message": "nope"}]}
    c = _client(
        httpx.MockTransport(lambda r: httpx.Response(422, json=body)),
    )
    with pytest.raises(KantataAPIError) as ei:
        c.get("/bad")
    assert ei.value.status_code == 422
    assert "422" in str(ei.value)
    c.close()


def test_invalid_json_raises() -> None:
    c = _client(
        httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                headers={"content-type": "application/json"},
                text="not-json{",
            )
        ),
    )
    with pytest.raises(KantataAPIError, match="Invalid JSON"):
        c.get("/x")
    c.close()


def test_non_json_success_returns_empty_dict() -> None:
    c = _client(
        httpx.MockTransport(
            lambda r: httpx.Response(200, headers={"content-type": "text/plain"}, text="ok")
        ),
    )
    assert c.get("/x") == {}
    c.close()


def test_request_error_wrapped() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.RequestError("offline", request=request)

    c = _client(httpx.MockTransport(boom))
    with pytest.raises(KantataAPIError, match="HTTP request failed"):
        c.get("/x")
    c.close()


def test_first_id_helper() -> None:
    payload = {
        "results": [{"key": "stories", "id": "42"}],
        "stories": {"42": {"id": "42", "title": "T"}},
    }
    assert KantataClient.first_id(payload) == "42"
    assert KantataClient.first_id({}) is None


def test_default_api_base_constant() -> None:
    assert "mavenlink" in DEFAULT_API_BASE


def test_context_manager_closes_underlying_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    with KantataClient(
        "t",
        api_base="https://test.invalid/api/v1",
        transport=httpx.MockTransport(handler),
    ) as c:
        c.get("/ping")
    # no exception after exit


def test_put_post_delete_delegate_to_request() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return httpx.Response(200, json={"m": request.method})

    c = _client(httpx.MockTransport(handler))
    c.post("/p", json_body={})
    c.put("/p", json_body={})
    c.delete("/p")
    assert methods == ["POST", "PUT", "DELETE"]
    c.close()
