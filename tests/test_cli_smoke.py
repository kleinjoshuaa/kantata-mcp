"""Smoke tests for Typer CLI (no Kantata network)."""

from __future__ import annotations

from unittest.mock import MagicMock

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
