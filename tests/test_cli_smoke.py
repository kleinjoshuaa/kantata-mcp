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


def test_login_defaults_to_local_flow(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    called = {"local": 0}

    def fake_local(*, redirect_port: int | None, open_browser: bool) -> None:
        assert redirect_port is None
        assert open_browser is True
        called["local"] += 1

    monkeypatch.setattr("kantata_assist.cli.login_interactive", fake_local)
    monkeypatch.setattr("kantata_assist.cli.login_via_broker", MagicMock)
    monkeypatch.setattr("kantata_assist.cli.load_oauth_broker_url", lambda: None)

    result = runner.invoke(app, ["login"])
    assert result.exit_code == 0
    assert called["local"] == 1


def test_login_uses_broker_flag(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    broker = MagicMock()
    monkeypatch.setattr("kantata_assist.cli.login_via_broker", broker)
    monkeypatch.setattr("kantata_assist.cli.login_interactive", MagicMock)
    monkeypatch.setattr("kantata_assist.cli.load_oauth_broker_url", lambda: None)

    result = runner.invoke(
        app,
        ["login", "--broker-url", "https://broker.example", "--poll-seconds", "1.5", "--timeout-seconds", "90"],
    )
    assert result.exit_code == 0
    broker.assert_called_once_with(
        broker_base_url="https://broker.example",
        open_browser=True,
        poll_interval_seconds=1.5,
        timeout_seconds=90.0,
    )


def test_login_uses_broker_env(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    broker = MagicMock()
    monkeypatch.setattr("kantata_assist.cli.login_via_broker", broker)
    monkeypatch.setattr("kantata_assist.cli.login_interactive", MagicMock)
    monkeypatch.setattr("kantata_assist.cli.load_oauth_broker_url", lambda: "https://broker.from.env")

    result = runner.invoke(app, ["login", "--no-browser"])
    assert result.exit_code == 0
    broker.assert_called_once_with(
        broker_base_url="https://broker.from.env",
        open_browser=False,
        poll_interval_seconds=2.0,
        timeout_seconds=300.0,
    )


def test_login_broker_browser_requires_broker_url(runner: CliRunner) -> None:
    result = runner.invoke(app, ["login", "--broker-browser"])
    assert result.exit_code != 0
    assert (
        "broker-browser" in (result.stdout + result.stderr).lower()
        or "broker" in (result.stdout + result.stderr).lower()
    )


def test_login_broker_browser_paste(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    opened: list[str] = []

    def fake_open(url: str) -> None:
        opened.append(url)

    monkeypatch.setattr(
        "kantata_assist.cli.broker_handoff_start_url", lambda u: "https://broker.example/exec?action=start"
    )
    monkeypatch.setattr("kantata_assist.cli.webbrowser.open", fake_open)
    monkeypatch.setattr("kantata_assist.cli.typer.prompt", lambda *a, **k: "  pasted-token  ")
    saved = MagicMock()
    monkeypatch.setattr("kantata_assist.cli.save_pasted_access_token", saved)
    monkeypatch.setattr("kantata_assist.cli.login_via_broker", MagicMock)

    result = runner.invoke(
        app,
        ["login", "--broker-url", "https://broker.example/exec", "--broker-browser"],
    )
    assert result.exit_code == 0
    assert opened == ["https://broker.example/exec?action=start"]
    saved.assert_called_once_with(access_token="pasted-token", token_type="bearer")
