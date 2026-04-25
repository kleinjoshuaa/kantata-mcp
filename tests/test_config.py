"""Tests for config credential loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kantata_assist.config import (
    default_credentials_path,
    load_access_token,
    load_api_base,
    save_credentials_from_payload,
)
from kantata_assist.operations import KantataOperations, operations_from_token


def test_default_credentials_path_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    p = tmp_path / "creds.json"
    monkeypatch.setenv("KANTATA_CREDENTIALS_PATH", str(p))
    assert default_credentials_path() == p


def test_default_credentials_path_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("KANTATA_CREDENTIALS_PATH", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_credentials_path() == tmp_path / ".config" / "kantata" / "credentials.json"


def test_save_credentials_from_payload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("KANTATA_CREDENTIALS_PATH", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    out_path = save_credentials_from_payload({"access_token": "  tok  ", "token_type": "Bearer"})
    assert out_path == tmp_path / ".config" / "kantata" / "credentials.json"
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data == {"access_token": "tok", "token_type": "Bearer"}


def test_save_credentials_from_payload_refresh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cred = tmp_path / "c.json"
    save_credentials_from_payload(
        {"access_token": "a", "refresh_token": " r "},
        credentials_path=cred,
    )
    data = json.loads(cred.read_text(encoding="utf-8"))
    assert data["access_token"] == "a"
    assert data["refresh_token"] == "r"
    assert data["token_type"] == "bearer"


def test_save_credentials_from_payload_requires_access_token(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="access_token"):
        save_credentials_from_payload({}, credentials_path=tmp_path / "x.json")


def test_load_access_token_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KANTATA_ACCESS_TOKEN", "  tok  ")
    monkeypatch.delenv("KANTATA_CREDENTIALS_PATH", raising=False)
    assert load_access_token() == "tok"


def test_load_access_token_empty_env_uses_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("KANTATA_ACCESS_TOKEN", "   ")
    cred = tmp_path / "c.json"
    cred.write_text(json.dumps({"access_token": "from-file"}), encoding="utf-8")
    assert load_access_token(credentials_path=cred) == "from-file"


def test_load_access_token_from_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("KANTATA_ACCESS_TOKEN", raising=False)
    cred = tmp_path / "c.json"
    cred.write_text(json.dumps({"access_token": "abc"}), encoding="utf-8")
    assert load_access_token(credentials_path=cred) == "abc"


def test_load_access_token_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("KANTATA_ACCESS_TOKEN", raising=False)
    p = tmp_path / "missing.json"
    with pytest.raises(RuntimeError, match="No Kantata access token"):
        load_access_token(credentials_path=p)


def test_load_api_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KANTATA_API_BASE", " https://x.example/api/v1 ")
    assert load_api_base() == "https://x.example/api/v1"
    monkeypatch.delenv("KANTATA_API_BASE", raising=False)
    assert load_api_base() is None


def test_operations_from_token_reads_default_credentials_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("KANTATA_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("KANTATA_CREDENTIALS_PATH", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    cred = tmp_path / ".config" / "kantata" / "credentials.json"
    cred.parent.mkdir(parents=True, exist_ok=True)
    cred.write_text(json.dumps({"access_token": "fromhome"}), encoding="utf-8")
    ops = operations_from_token(api_base="https://example.invalid/api/v1")
    assert isinstance(ops, KantataOperations)
    assert ops._c._client.headers["Authorization"] == "Bearer fromhome"  # noqa: SLF001
    assert str(ops._c._client.base_url).rstrip("/") == "https://example.invalid/api/v1"  # noqa: SLF001
    ops._c.close()  # noqa: SLF001


def test_operations_from_token_explicit_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KANTATA_ACCESS_TOKEN", raising=False)
    ops = operations_from_token(access_token="direct", api_base="https://x/api/v1")
    assert ops._c._client.headers["Authorization"] == "Bearer direct"  # noqa: SLF001
    ops._c.close()  # noqa: SLF001
