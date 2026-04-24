"""Load access token and optional API base from env or credentials file."""

from __future__ import annotations

import json
import os
from pathlib import Path


def default_credentials_path() -> Path:
    env = os.environ.get("KANTATA_CREDENTIALS_PATH")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".config" / "kantata" / "credentials.json"


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
        "No Kantata access token: set KANTATA_ACCESS_TOKEN or run `kantata login` "
        f"(credentials file: {path})"
    )


def load_api_base() -> str | None:
    b = os.environ.get("KANTATA_API_BASE")
    return b.strip() if b else None
