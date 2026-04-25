"""Tests for OAuth helpers (no real Kantata network)."""

from __future__ import annotations

import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import HTTPServer
from pathlib import Path

import httpx
import pytest

from kantata_assist.oauth import (
    DEFAULT_OAUTH_CALLBACK_PORT,
    _OAuthHandler,
    _require_env,
    _resolve_redirect_port,
    broker_handoff_start_url,
    exchange_code_for_token,
    login_interactive,
    login_via_broker,
    save_pasted_access_token,
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


def test_login_via_broker_success(tmp_path: Path) -> None:
    calls = {"poll": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/start":
            return httpx.Response(
                200,
                json={
                    "session_id": "s-1",
                    "authorize_url": "https://broker.example/auth",
                    "poll_url": "https://broker.example/poll",
                    "poll_token": "pt",
                },
            )
        if request.method == "GET" and request.url.path == "/poll":
            calls["poll"] += 1
            if calls["poll"] == 1:
                return httpx.Response(200, json={"status": "pending"})
            q = urllib.parse.parse_qs(request.url.query.decode())
            assert q["session_id"] == ["s-1"]
            assert q["poll_token"] == ["pt"]
            return httpx.Response(200, json={"status": "complete", "access_token": "abc", "token_type": "bearer"})
        raise AssertionError(request.url)

    cpath = tmp_path / "creds.json"
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        out = login_via_broker(
            broker_base_url="https://broker.example",
            open_browser=False,
            poll_interval_seconds=0.01,
            timeout_seconds=2,
            credentials_path=cpath,
            http_client=client,
        )
    finally:
        client.close()
    assert out == cpath
    assert "abc" in cpath.read_text(encoding="utf-8")


def test_login_via_broker_start_missing_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"session_id": "x"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(RuntimeError, match="Broker start failed"):
            login_via_broker(
                broker_base_url="https://broker.example",
                open_browser=False,
                http_client=client,
            )
    finally:
        client.close()


def test_login_via_broker_query_style_apps_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Apps Script uses ?action=start|poll on the /exec URL; /exec/start is not a valid path."""
    monkeypatch.delenv("KANTATA_OAUTH_BROKER_STYLE", raising=False)
    calls = {"poll": 0}
    base = "https://script.google.com/macros/s/ABC123/exec"

    def handler(request: httpx.Request) -> httpx.Response:
        u = request.url
        path = u.path
        q = urllib.parse.parse_qs(u.query.decode())
        if path.endswith("/exec/start"):
            return httpx.Response(302, headers={"Location": "https://accounts.google.com/ServiceLogin"})
        if path.endswith("/exec") and q.get("action") == ["start"]:
            return httpx.Response(
                200,
                json={
                    "session_id": "s-gas",
                    "authorize_url": "https://app.mavenlink.com/oauth/authorize",
                    "poll_url": base + "?action=poll",
                    "poll_token": "pt-gas",
                },
            )
        if path.endswith("/exec") and q.get("action") == ["poll"]:
            calls["poll"] += 1
            if calls["poll"] == 1:
                return httpx.Response(200, json={"status": "pending"})
            assert q["session_id"] == ["s-gas"]
            assert q["poll_token"] == ["pt-gas"]
            return httpx.Response(200, json={"status": "complete", "access_token": "tok-gas"})
        raise AssertionError(str(u))

    cpath = tmp_path / "creds.json"
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        out = login_via_broker(
            broker_base_url=base,
            open_browser=False,
            poll_interval_seconds=0.01,
            timeout_seconds=2,
            credentials_path=cpath,
            http_client=client,
        )
    finally:
        client.close()
    assert out == cpath
    assert "tok-gas" in cpath.read_text(encoding="utf-8")


def test_login_via_broker_query_style_pasted_exec_with_action_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pasting .../exec?action=start must not become .../exec?action=start/start."""
    monkeypatch.delenv("KANTATA_OAUTH_BROKER_STYLE", raising=False)
    calls = {"poll": 0}
    base = "https://script.google.com/macros/s/ABC123/exec"
    pasted = base + "?action=start"

    def handler(request: httpx.Request) -> httpx.Response:
        u = request.url
        path = u.path
        q = urllib.parse.parse_qs(u.query.decode())
        assert "start/start" not in str(u)
        if path.endswith("/exec/start"):
            return httpx.Response(302, headers={"Location": "https://accounts.google.com/ServiceLogin"})
        if path.endswith("/exec") and q.get("action") == ["start"]:
            return httpx.Response(
                200,
                json={
                    "session_id": "s-gas",
                    "authorize_url": "https://app.mavenlink.com/oauth/authorize",
                    "poll_url": base + "?action=poll",
                    "poll_token": "pt-gas",
                },
            )
        if path.endswith("/exec") and q.get("action") == ["poll"]:
            calls["poll"] += 1
            if calls["poll"] == 1:
                return httpx.Response(200, json={"status": "pending"})
            return httpx.Response(200, json={"status": "complete", "access_token": "tok-gas"})
        raise AssertionError(str(u))

    cpath = tmp_path / "creds.json"
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        out = login_via_broker(
            broker_base_url=pasted,
            open_browser=False,
            poll_interval_seconds=0.01,
            timeout_seconds=2,
            credentials_path=cpath,
            http_client=client,
        )
    finally:
        client.close()
    assert out == cpath
    assert "tok-gas" in cpath.read_text(encoding="utf-8")


def test_login_via_broker_style_path_forces_path_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KANTATA_OAUTH_BROKER_STYLE", "path")

    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if p.endswith("/exec/start"):
            return httpx.Response(
                200,
                json={
                    "session_id": "s-path",
                    "authorize_url": "https://broker.example/auth",
                },
            )
        if p.endswith("/exec/poll"):
            return httpx.Response(200, json={"status": "complete", "access_token": "only-path"})
        return httpx.Response(404)

    cpath = tmp_path / "creds.json"
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        login_via_broker(
            broker_base_url="https://script.google.com/macros/s/X/exec",
            open_browser=False,
            poll_interval_seconds=0.01,
            timeout_seconds=2,
            credentials_path=cpath,
            http_client=client,
        )
    finally:
        client.close()
    assert "only-path" in cpath.read_text(encoding="utf-8")


def test_login_via_broker_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(
                200,
                json={"session_id": "s-1", "authorize_url": "https://broker.example/auth"},
            )
        return httpx.Response(200, json={"status": "error", "error": "denied"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(RuntimeError, match="Broker OAuth error: denied"):
            login_via_broker(
                broker_base_url="https://broker.example",
                open_browser=False,
                http_client=client,
            )
    finally:
        client.close()


def test_login_via_broker_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(
                200,
                json={"session_id": "s-1", "authorize_url": "https://broker.example/auth"},
            )
        return httpx.Response(200, json={"status": "pending"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(RuntimeError, match="Timed out"):
            login_via_broker(
                broker_base_url="https://broker.example",
                open_browser=False,
                poll_interval_seconds=0.01,
                timeout_seconds=0.01,
                http_client=client,
            )
    finally:
        client.close()


def test_broker_handoff_start_url_apps_script_query_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KANTATA_OAUTH_BROKER_STYLE", raising=False)
    u = broker_handoff_start_url("https://script.google.com/macros/s/ABC/exec")
    assert "action=start" in u
    assert u.startswith("https://script.google.com/")


def test_save_pasted_access_token_writes_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    c = tmp_path / "creds.json"
    monkeypatch.setenv("KANTATA_CREDENTIALS_PATH", str(c))
    out = save_pasted_access_token(access_token="  tok9  ", token_type="Bearer")
    assert out == c
    data = c.read_text(encoding="utf-8")
    assert "tok9" in data
    assert "Bearer" in data
