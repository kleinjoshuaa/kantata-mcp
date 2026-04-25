"""Smoke tests for Typer CLI (no Kantata network)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from kantata_assist.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_whoami_cli_json(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    ops = MagicMock()
    ops.whoami.return_value = {"user": {"id": "99", "full_name": "Test"}}
    monkeypatch.setattr("kantata_assist.cli.operations_from_token", lambda: ops)
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 0
    assert "99" in result.stdout
    ops.whoami.assert_called_once()


def test_list_users_requires_filter(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    monkeypatch.setattr("kantata_assist.cli.operations_from_token", MagicMock)
    result = runner.invoke(app, ["list-users"])
    assert result.exit_code == 1
    combined = (result.stdout or "") + (result.stderr or "")
    assert "at least one" in combined.lower()


def test_list_users_delegates(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    ops = MagicMock()
    ops.list_users.return_value = {"items": [], "meta": {"count": 0}}
    monkeypatch.setattr("kantata_assist.cli.operations_from_token", lambda: ops)
    result = runner.invoke(app, ["list-users", "--workspace", "3"])
    assert result.exit_code == 0
    ops.list_users.assert_called_once_with(
        workspace_id="3",
        search=None,
        by_email_address=None,
        on_my_account=False,
    )


def test_import_credentials_stdin(monkeypatch: pytest.MonkeyPatch, runner: CliRunner, tmp_path: Path) -> None:
    monkeypatch.setenv("KANTATA_CREDENTIALS_PATH", str(tmp_path / "c.json"))
    payload = json.dumps({"access_token": "from-stdin", "token_type": "bearer"})
    result = runner.invoke(app, ["import-credentials"], input=payload + "\n")
    assert result.exit_code == 0
    assert "Wrote credentials" in result.stdout
    out = tmp_path / "c.json"
    assert json.loads(out.read_text(encoding="utf-8"))["access_token"] == "from-stdin"


def test_import_credentials_file(monkeypatch: pytest.MonkeyPatch, runner: CliRunner, tmp_path: Path) -> None:
    monkeypatch.setenv("KANTATA_CREDENTIALS_PATH", str(tmp_path / "out.json"))
    src = tmp_path / "in.json"
    src.write_text(json.dumps({"access_token": "from-file"}), encoding="utf-8")
    result = runner.invoke(app, ["import-credentials", "--file", str(src)])
    assert result.exit_code == 0
    assert json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))["access_token"] == "from-file"


def test_import_credentials_invalid_json(monkeypatch: pytest.MonkeyPatch, runner: CliRunner, tmp_path: Path) -> None:
    monkeypatch.setenv("KANTATA_CREDENTIALS_PATH", str(tmp_path / "c.json"))
    result = runner.invoke(app, ["import-credentials"], input="not json\n")
    assert result.exit_code == 1
    assert "Invalid JSON" in (result.stdout or "") + (result.stderr or "")


def test_import_credentials_missing_access_token(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner, tmp_path: Path
) -> None:
    monkeypatch.setenv("KANTATA_CREDENTIALS_PATH", str(tmp_path / "c.json"))
    result = runner.invoke(app, ["import-credentials"], input="{}\n")
    assert result.exit_code == 1
    combined = (result.stdout or "") + (result.stderr or "")
    assert "access_token" in combined


def test_import_credentials_rejects_tty_stdin(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    monkeypatch.delenv("KANTATA_CREDENTIALS_PATH", raising=False)
    stdin_mock = MagicMock()
    stdin_mock.isatty.return_value = True
    with patch("kantata_assist.cli.sys.stdin", stdin_mock):
        result = runner.invoke(app, ["import-credentials"])
    assert result.exit_code == 1
    combined = (result.stdout or "") + (result.stderr or "")
    assert "stdin" in combined.lower() or "--file" in combined.lower()
