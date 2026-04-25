"""Load access token and optional API base from env or credentials file."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def default_credentials_path() -> Path:
    env = os.environ.get("KANTATA_CREDENTIALS_PATH")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".config" / "kantata" / "credentials.json"


def save_credentials_from_payload(
    data: Mapping[str, Any],
    *,
    credentials_path: Path | None = None,
) -> Path:
    """
    Write credentials.json from a token payload (e.g. Kantata /oauth/token JSON or import).

    Persists access_token, token_type (default bearer), and refresh_token when present.
    """
    access = data.get("access_token")
    if not isinstance(access, str) or not access.strip():
        msg = 'Credentials JSON must contain a non-empty string "access_token".'
        raise ValueError(msg)
    out: dict[str, str] = {"access_token": access.strip()}
    tt = data.get("token_type")
    out["token_type"] = tt.strip() if isinstance(tt, str) and tt.strip() else "bearer"
    rt = data.get("refresh_token")
    if isinstance(rt, str) and rt.strip():
        out["refresh_token"] = rt.strip()
    path = credentials_path or default_credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def load_access_token(*, credentials_path: Path | None = None) -> str:
    # Treat unset or whitespace-only as "use credentials file" so MCP configs
    # that set KANTATA_ACCESS_TOKEN="" do not block reading ~/.config/.../credentials.json.
    token = os.environ.get("KANTATA_ACCESS_TOKEN")
    if token is not None and str(token).strip():
        return str(token).strip()
    path = credentials_path or default_credentials_path()
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        t = data.get("access_token")
        if isinstance(t, str) and t.strip():
            return t.strip()
    raise RuntimeError(
        "No Kantata access token: set KANTATA_ACCESS_TOKEN, run `kantata login`, "
        "or `kantata import-credentials` "
        f"(credentials file: {path})"
    )


def load_api_base() -> str | None:
    b = os.environ.get("KANTATA_API_BASE")
    return b.strip() if b else None
