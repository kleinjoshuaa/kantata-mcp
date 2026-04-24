"""Smoke tests for MCP tool callables (patched ops, no network)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from kantata_assist import mcp_server


def test_kantata_whoami_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    ops = MagicMock()
    ops.whoami.return_value = {"user": {"id": "1"}}
    monkeypatch.setattr(mcp_server, "_ops", lambda: ops)
    out = mcp_server.kantata_whoami()
    assert "1" in out
    assert "user" in out
    ops.whoami.assert_called_once()


def test_kantata_list_projects_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    ops = MagicMock()
    ops.list_my_projects.return_value = {"items": [], "meta": {"count": 0}}
    monkeypatch.setattr(mcp_server, "_ops", lambda: ops)
    mcp_server.kantata_list_projects(search=None)
    ops.list_my_projects.assert_called_once_with(search=None)


def test_kantata_post_project_update_file_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    ops = MagicMock()
    monkeypatch.setattr(mcp_server, "_ops", lambda: ops)

    def boom(**_kwargs: object) -> dict:
        raise FileNotFoundError("/no/such/file")

    ops.post_project_update.side_effect = boom
    out = mcp_server.kantata_post_project_update(
        workspace_id="1",
        message="hi",
        attachment_paths=["/no/such/file"],
        attachment_ids=None,
    )
    assert "error" in out
    assert "/no/such/file" in out
