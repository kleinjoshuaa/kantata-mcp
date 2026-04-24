"""Tests for OAuth helpers (no real Kantata network)."""

from __future__ import annotations

import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import HTTPServer

import httpx
import pytest

from kantata_assist.oauth import (
    DEFAULT_OAUTH_CALLBACK_PORT,
    _OAuthHandler,
    _require_env,
    _resolve_redirect_port,
    exchange_code_for_token,
    login_interactive,
)


def test_require_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KANTATA_CLIENT_ID", raising=False)
    with pytest.raises(RuntimeError, match="KANTATA_CLIENT_ID"):
        _require_env("KANTATA_CLIENT_ID")


def test_require_env_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KANTATA_CLIENT_ID", "  x  ")
    assert _require_env("KANTATA_CLIENT_ID") == "x"


def test_resolve_redirect_port_explicit() -> None:
    assert _resolve_redirect_port(9999) == 9999


def test_resolve_redirect_port_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KANTATA_OAUTH_CALLBACK_PORT", "7654")
    assert _resolve_redirect_port(None) == 7654


def test_resolve_redirect_port_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KANTATA_OAUTH_CALLBACK_PORT", raising=False)
    assert _resolve_redirect_port(None) == DEFAULT_OAUTH_CALLBACK_PORT


def test_exchange_code_for_token_uses_post_body() -> None:
    captured: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        return httpx.Response(200, json={"access_token": "at", "token_type": "bearer"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        out = exchange_code_for_token(
            code="c1",
            client_id="id",
            client_secret="sec",
            redirect_uri="http://127.0.0.1:8765/callback",
            token_url="https://oauth.test/token",
            http_client=client,
        )
    finally:
        client.close()
    assert out["access_token"] == "at"
    parsed = urllib.parse.parse_qs(captured["body"].decode())
    assert parsed["grant_type"] == ["authorization_code"]
    assert parsed["code"] == ["c1"]
    assert parsed["client_id"] == ["id"]
    assert parsed["client_secret"] == ["sec"]
    assert parsed["redirect_uri"] == ["http://127.0.0.1:8765/callback"]


def test_exchange_code_for_token_raises_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(httpx.HTTPStatusError):
            exchange_code_for_token(
                code="c",
                client_id="i",
                client_secret="s",
                redirect_uri="http://127.0.0.1/cb",
                http_client=client,
            )
    finally:
        client.close()


def _serve_one(handler_cls: type, path_qs: str, *, allow_http_error: bool = False) -> None:
    _OAuthHandler.code_holder["code"] = None
    _OAuthHandler.code_holder["error"] = None
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_address[1]

    def run() -> None:
        server.handle_request()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    try:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}{path_qs}", timeout=5)
        except urllib.error.HTTPError:
            if not allow_http_error:
                raise
    finally:
        t.join(timeout=5)
        server.server_close()


def test_oauth_handler_accepts_code() -> None:
    _serve_one(_OAuthHandler, "/callback?code=mycode")
    assert _OAuthHandler.code_holder["code"] == "mycode"
    assert _OAuthHandler.code_holder["error"] is None


def test_oauth_handler_error_query() -> None:
    _serve_one(_OAuthHandler, "/callback?error=access_denied&error_description=nope", allow_http_error=True)
    assert _OAuthHandler.code_holder["code"] is None
    assert _OAuthHandler.code_holder["error"] == "nope"


def test_oauth_handler_no_query_404() -> None:
    server = HTTPServer(("127.0.0.1", 0), _OAuthHandler)
    port = server.server_address[1]

    def run() -> None:
        server.handle_request()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    try:
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(f"http://127.0.0.1:{port}/nope", timeout=5)
    finally:
        t.join(timeout=5)
        server.server_close()


def test_login_interactive_missing_client_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KANTATA_CLIENT_ID", raising=False)
    monkeypatch.delenv("KANTATA_CLIENT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="KANTATA_CLIENT_ID"):
        login_interactive(open_browser=False)
