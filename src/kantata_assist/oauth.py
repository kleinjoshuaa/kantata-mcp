"""OAuth2 authorization-code helper for Kantata (app.mavenlink.com)."""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

import httpx

DEFAULT_AUTHORIZE = "https://app.mavenlink.com/oauth/authorize"
DEFAULT_TOKEN = "https://app.mavenlink.com/oauth/token"
# Single well-known port so Kantata OAuth apps can register one redirect URI:
#   http://127.0.0.1:8765/callback
DEFAULT_OAUTH_CALLBACK_PORT = 8765


def _require_env(name: str) -> str:
    v = os.environ.get(name)
    if not v or not str(v).strip():
        raise RuntimeError(f"Missing environment variable: {name}")
    return str(v).strip()


class _OAuthHandler(BaseHTTPRequestHandler):
    code_holder: dict[str, str | None] = {"code": None, "error": None}

    def do_GET(self) -> None:  # noqa: N802
        path = self.path
        if "?" not in path:
            self.send_response(404)
            self.end_headers()
            return
        _, q = path.split("?", 1)
        qs = urllib.parse.parse_qs(q)
        if "code" in qs and qs["code"]:
            _OAuthHandler.code_holder["code"] = qs["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>Kantata login successful. You can close this window.</body></html>")
        elif "error" in qs:
            _OAuthHandler.code_holder["error"] = qs.get("error_description", qs["error"])[0]
            self.send_response(400)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OAuth error. Check the terminal.")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def exchange_code_for_token(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    token_url: str = DEFAULT_TOKEN,
    http_client: httpx.Client | None = None,
) -> dict:
    """Exchange authorization code for tokens. Pass http_client for tests (MockTransport)."""
    owns = http_client is None
    client = http_client or httpx.Client(timeout=60.0)
    try:
        r = client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        r.raise_for_status()
        return r.json()
    finally:
        if owns:
            client.close()


def _resolve_redirect_port(explicit: int | None) -> int:
    """CLI --port wins; else KANTATA_OAUTH_CALLBACK_PORT; else DEFAULT_OAUTH_CALLBACK_PORT."""
    if explicit is not None:
        return explicit
    env = os.environ.get("KANTATA_OAUTH_CALLBACK_PORT", "").strip()
    if env.isdigit():
        return int(env)
    return DEFAULT_OAUTH_CALLBACK_PORT


def _resolve_credentials_path(credentials_path: Path | None = None) -> Path:
    path = credentials_path or Path(os.environ.get("KANTATA_CREDENTIALS_PATH") or "").expanduser()
    if not path or str(path) == ".":
        path = Path.home() / ".config" / "kantata" / "credentials.json"
    return path


def _write_credentials_file(
    *,
    access_token: str,
    token_type: str = "bearer",
    credentials_path: Path | None = None,
) -> Path:
    token = access_token.strip()
    if not token:
        raise RuntimeError("Cannot write empty access token")
    path = _resolve_credentials_path(credentials_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = {"access_token": token, "token_type": token_type}
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    print(f"Wrote credentials to {path}")
    return path


def save_pasted_access_token(
    *,
    access_token: str,
    token_type: str = "bearer",
    credentials_path: Path | None = None,
) -> Path:
    """Write the credentials file from a pasted Kantata OAuth access token (browser broker handoff)."""
    return _write_credentials_file(
        access_token=access_token,
        token_type=token_type,
        credentials_path=credentials_path,
    )


def _merge_url_query_params(url: str, params: dict[str, str]) -> str:
    """Merge query keys into *url* (httpx ``params=`` would replace an existing query string)."""
    parts = urllib.parse.urlsplit(url.strip())
    q = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    for k, v in params.items():
        if v != "":
            q[k] = v
    new_query = urllib.parse.urlencode(q)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


def _broker_path_base_and_preserved_query(broker_base_url: str) -> tuple[str, dict[str, str]]:
    """Path-only URL (no ``?``) plus query params to re-attach (excluding ``action``).

    Users often paste ``.../exec?action=start``; appending ``/start`` to the full string produced
    ``...?action=start/start``. We strip ``action`` and any fragment, then rebuild ``/start`` or
    ``?action=`` on the path base only.
    """
    parts = urllib.parse.urlsplit(broker_base_url.strip())
    q = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    q.pop("action", None)
    path = (parts.path or "").rstrip("/")
    base_path = urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, "", ""))
    return base_path, q


def _broker_url(base: str, endpoint: str) -> str:
    base_path, preserved = _broker_path_base_and_preserved_query(base)
    ep = endpoint if endpoint.startswith("/") else f"/{endpoint}"
    out = f"{base_path}{ep}"
    if preserved:
        out = _merge_url_query_params(out, preserved)
    return out


def _broker_append_query_action(base: str, action: str) -> str:
    """Same entrypoint as path-style brokers, using ?action= (e.g. Google Apps Script Web App)."""
    base_path, preserved = _broker_path_base_and_preserved_query(base)
    merged = {**preserved, "action": action}
    query = urllib.parse.urlencode(merged)
    parts = urllib.parse.urlsplit(base_path)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def _broker_prefer_query_first(broker_base_url: str) -> bool:
    """Heuristic: Apps Script deploy URLs need ?action=… on the /exec URL, not /exec/start."""
    parts = urllib.parse.urlsplit(broker_base_url.strip())
    netloc = (parts.netloc or "").lower()
    path = parts.path or ""
    if "script.google.com" in netloc:
        return True
    if "/macros/" in path:
        return True
    return False


def _broker_start_url_candidates(broker_base_url: str) -> list[str]:
    """Path style GET {base}/start, or query style GET {base}?action=start (both supported)."""
    style = (os.environ.get("KANTATA_OAUTH_BROKER_STYLE") or "auto").strip().lower()
    path_u = _broker_url(broker_base_url, "/start")
    query_u = _broker_append_query_action(broker_base_url, "start")
    if style in ("path", "rest", "default"):
        return [path_u]
    if style in ("query", "apps_script", "google_apps_script", "gas"):
        return [query_u]
    if _broker_prefer_query_first(broker_base_url):
        return [query_u, path_u]
    return [path_u, query_u]


def _default_poll_url(*, broker_base_url: str, used_query_start: bool) -> str:
    if used_query_start:
        return _broker_append_query_action(broker_base_url, "poll")
    return _broker_url(broker_base_url, "/poll")


def broker_handoff_start_url(broker_base_url: str) -> str:
    """First broker ``start`` URL for this base (same order as :func:`login_via_broker` tries).

    Open this URL in a normal browser when using manual handoff (Workspace-gated Apps Script, etc.).
    """
    cands = _broker_start_url_candidates(broker_base_url)
    if not cands:
        raise RuntimeError("No broker start URL candidates")
    return cands[0]


def _parse_broker_start_payload(resp: httpx.Response) -> dict[str, object] | None:
    if resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    session_id = str(data.get("session_id") or "").strip()
    authorize_url = str(data.get("authorize_url") or "").strip()
    if not session_id or not authorize_url:
        return None
    return data


def login_via_broker(
    *,
    broker_base_url: str,
    open_browser: bool = True,
    poll_interval_seconds: float = 2.0,
    timeout_seconds: float = 300.0,
    credentials_path: Path | None = None,
    http_client: httpx.Client | None = None,
) -> Path:
    """Brokered OAuth login via external callback service.

    Supports two start/poll URL shapes (see ``KANTATA_OAUTH_BROKER_STYLE``):

    - **Path (REST):** ``GET {base}/start`` and ``GET {base}/poll`` (or ``poll_url`` from JSON).
    - **Query (Apps Script):** ``GET {base}?action=start`` and ``GET {base}?action=poll`` (or
      ``poll_url`` from JSON). Required for Google Apps Script web apps whose handler is a single
      ``/exec`` URL.

    Auto mode tries path first for generic brokers, and query first when the base URL looks like
    Apps Script (``script.google.com`` or ``/macros/`` in the path).
    """
    owns = http_client is None
    client = http_client or httpx.Client(timeout=30.0)
    try:
        start_data: dict[str, object] | None = None
        used_query_start = False
        last_start_error: str | None = None
        for cand in _broker_start_url_candidates(broker_base_url):
            used_query_start = urllib.parse.parse_qs(urllib.parse.urlsplit(cand).query).get("action") == ["start"]
            try:
                start = client.get(
                    cand,
                    headers={"Accept": "application/json"},
                    follow_redirects=False,
                )
            except httpx.RequestError as exc:
                last_start_error = str(exc)
                continue
            parsed = _parse_broker_start_payload(start)
            if parsed is not None:
                start_data = parsed
                break
            if start.status_code in (301, 302, 303, 307, 308):
                loc = (start.headers.get("location") or start.headers.get("Location") or "").strip()
                loc_note = f" Location: {loc[:120]}..." if len(loc) > 120 else (f" Location: {loc}" if loc else "")
                last_start_error = (
                    f"HTTP {start.status_code} from {cand!r}.{loc_note} "
                    "(wrong URL shape, or broker requires a browser session; "
                    "see README broker and Google Apps Script deploy notes.)"
                )
                continue
            try:
                body_preview = (start.text or "")[:200]
            except Exception:
                body_preview = ""
            last_start_error = f"HTTP {start.status_code} from {cand!r}: {body_preview!r}"

        if start_data is None:
            hint = (
                " Set KANTATA_OAUTH_BROKER_STYLE=query for ?action=start brokers "
                "(e.g. Google Apps Script), or =path for /start only."
            )
            if _broker_prefer_query_first(broker_base_url):
                hint += (
                    " Google Apps Script: use the web app URL ending in /exec without pasting ?action=start "
                    "(the CLI adds it). If you still get HTTP 302, redeploy with Who has access: Anyone "
                    "so unauthenticated GETs reach doGet; Workspace-only access often redirects this client "
                    "to Google Sign-In and cannot return JSON."
                )
            raise RuntimeError(
                "Broker start failed: no JSON with session_id and authorize_url from any start URL."
                + (f" Last: {last_start_error}." if last_start_error else "")
                + hint
            )

        session_id = str(start_data.get("session_id") or "").strip()
        authorize_url = str(start_data.get("authorize_url") or "").strip()

        poll_raw = start_data.get("poll_url")
        poll_url = (
            str(poll_raw).strip()
            if isinstance(poll_raw, str) and str(poll_raw).strip()
            else _default_poll_url(broker_base_url=broker_base_url, used_query_start=used_query_start)
        )
        poll_token = str(start_data.get("poll_token") or "").strip()

        print(f"Broker login session: {session_id}")
        print("Open this URL to authenticate (if browser does not open):\n", authorize_url, sep="")
        if open_browser:
            webbrowser.open(authorize_url)

        deadline = time.monotonic() + max(1.0, timeout_seconds)
        sleep_for = max(0.2, poll_interval_seconds)
        while time.monotonic() < deadline:
            poll_params: dict[str, str] = {"session_id": session_id}
            if poll_token:
                poll_params["poll_token"] = poll_token
            poll_target = _merge_url_query_params(poll_url, poll_params)
            poll = client.get(poll_target, headers={"Accept": "application/json"})
            poll.raise_for_status()
            payload = poll.json()
            if not isinstance(payload, dict):
                raise RuntimeError(f"Unexpected broker /poll payload: {payload!r}")
            status = str(payload.get("status") or "").strip().lower()
            if status == "pending":
                time.sleep(sleep_for)
                continue
            if status == "expired":
                raise RuntimeError("Broker OAuth session expired before completion")
            if status == "error":
                msg = str(payload.get("error") or payload.get("message") or "unknown broker error").strip()
                raise RuntimeError(f"Broker OAuth error: {msg}")
            if status == "complete":
                access = payload.get("access_token")
                if not isinstance(access, str) or not access.strip():
                    raise RuntimeError(f"Broker /poll complete missing access_token: {payload!r}")
                token_type = payload.get("token_type")
                if isinstance(token_type, str) and token_type.strip():
                    tt = token_type.strip()
                else:
                    tt = "bearer"
                return _write_credentials_file(
                    access_token=access.strip(),
                    token_type=tt,
                    credentials_path=credentials_path,
                )
            raise RuntimeError(f"Unknown broker /poll status {status!r} (payload: {payload!r})")
        raise RuntimeError("Timed out waiting for broker OAuth completion")
    finally:
        if owns:
            client.close()


def login_interactive(
    *,
    redirect_port: int | None = None,
    open_browser: bool = True,
    authorize_url: str | None = None,
    token_url: str | None = None,
    credentials_path: Path | None = None,
) -> Path:
    """
    Run local redirect server, open browser, exchange code, write credentials file.
    """
    client_id = _require_env("KANTATA_CLIENT_ID")
    client_secret = _require_env("KANTATA_CLIENT_SECRET")
    auth_base = authorize_url or os.environ.get("KANTATA_OAUTH_AUTHORIZE") or DEFAULT_AUTHORIZE
    tok_base = token_url or os.environ.get("KANTATA_OAUTH_TOKEN") or DEFAULT_TOKEN
    _OAuthHandler.code_holder["code"] = None
    _OAuthHandler.code_holder["error"] = None

    port = _resolve_redirect_port(redirect_port)
    try:
        server = HTTPServer(("127.0.0.1", port), _OAuthHandler)
    except OSError as e:
        raise RuntimeError(
            f"Cannot bind OAuth callback on 127.0.0.1:{port} ({e}). "
            "Free the port, or run with a different `--port` and add that redirect URI "
            "to your Kantata OAuth app, or set KANTATA_OAUTH_CALLBACK_PORT."
        ) from e
    port = int(server.server_address[1])
    redirect_uri = f"http://127.0.0.1:{port}/callback"

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
    }
    auth_url = f"{auth_base}?{urllib.parse.urlencode(params)}"

    print(f"Listening on {redirect_uri}")
    print("If the browser does not open, visit:\n", auth_url, sep="")

    if open_browser:
        webbrowser.open(auth_url)

    def serve_one() -> None:
        server.handle_request()

    t = Thread(target=serve_one, daemon=True)
    t.start()
    t.join(timeout=300)
    if t.is_alive():
        server.shutdown()
        raise RuntimeError("Timed out waiting for OAuth redirect")

    code = _OAuthHandler.code_holder["code"]
    err = _OAuthHandler.code_holder["error"]
    if err:
        raise RuntimeError(f"OAuth error: {err}")
    if not code:
        raise RuntimeError("No authorization code received")

    token_payload = exchange_code_for_token(
        code=code,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        token_url=tok_base,
    )
    access = token_payload.get("access_token")
    if not isinstance(access, str):
        raise RuntimeError(f"Unexpected token response: {token_payload!r}")
    token_type = token_payload.get("token_type")
    tt = token_type.strip() if isinstance(token_type, str) and token_type.strip() else "bearer"
    return _write_credentials_file(access_token=access, token_type=tt, credentials_path=credentials_path)
