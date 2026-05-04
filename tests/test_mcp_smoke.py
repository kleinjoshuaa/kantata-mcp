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


def test_kantata_update_time_entry_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    ops = MagicMock()
    ops.update_time_entry.return_value = {"items": [{"id": "1"}], "meta": {"count": 1}}
    monkeypatch.setattr(mcp_server, "_ops", lambda: ops)
    out = mcp_server.kantata_update_time_entry(
        time_entry_id="1",
        notes="x",
        date_performed=None,
        time_in_minutes=None,
        story_id=None,
        billable=None,
    )
    assert "1" in out
    ops.update_time_entry.assert_called_once_with(
        time_entry_id="1",
        notes="x",
        date_performed=None,
        time_in_minutes=None,
        story_id=None,
        billable=None,
    )


def test_kantata_update_task_status_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    ops = MagicMock()
    ops.get_story.return_value = {"story": {"title": "Existing"}}
    ops.upsert_task.return_value = {"items": [{"id": "5"}], "meta": {"count": 1}}
    monkeypatch.setattr(mcp_server, "_ops", lambda: ops)
    out = mcp_server.kantata_update_task(
        story_id="5",
        title=None,
        description=None,
        parent_story_id=None,
        assign_me=False,
        story_type=None,
        status="Completed",
    )
    assert "5" in out
    ops.upsert_task.assert_called_once_with(
        workspace_id="",
        title="Existing",
        story_id="5",
        description=None,
        parent_story_id=None,
        assignee_user_ids=None,
        story_type=None,
        status="Completed",
    )


def test_kantata_update_post_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    ops = MagicMock()
    ops.update_post.return_value = {"items": [{"id": "1"}], "meta": {"count": 1}}
    monkeypatch.setattr(mcp_server, "_ops", lambda: ops)
    out = mcp_server.kantata_update_post(post_id="1", message="hi", story_id=None)
    assert "1" in out
    ops.update_post.assert_called_once_with(post_id="1", message="hi", story_id=None)


def test_kantata_update_post_tool_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    ops = MagicMock()

    def boom(**_kwargs: object) -> dict:
        raise ValueError("Provide at least one")

    ops.update_post.side_effect = boom
    monkeypatch.setattr(mcp_server, "_ops", lambda: ops)
    out = mcp_server.kantata_update_post(post_id="1", message=None, story_id=None)
    assert "error" in out


def test_kantata_log_time_off_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    ops = MagicMock()
    ops.create_time_off_entries.return_value = {"items": [{"id": "1"}], "meta": {"count": 1}}
    monkeypatch.setattr(mcp_server, "_ops", lambda: ops)
    out = mcp_server.kantata_log_time_off(hours=8.0, requested_dates="2026-04-20,2026-04-21", user_id=None)
    assert "1" in out
    ops.create_time_off_entries.assert_called_once_with(
        requested_dates=["2026-04-20", "2026-04-21"],
        hours=8.0,
        user_id=None,
    )


def test_kantata_list_time_off_entries_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    ops = MagicMock()
    ops.list_time_off_entries.return_value = {"items": [], "meta": {"count": 0}}
    monkeypatch.setattr(mcp_server, "_ops", lambda: ops)
    mcp_server.kantata_list_time_off_entries(
        start_date="2026-01-01",
        end_date=None,
        user_id=None,
        only_mine=True,
        workspace_id=None,
        include=None,
    )
    ops.list_time_off_entries.assert_called_once_with(
        start_date="2026-01-01",
        end_date=None,
        user_id=None,
        only_mine=True,
        workspace_id=None,
        include=None,
    )


def test_kantata_link_post_to_task_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    ops = MagicMock()
    ops.update_post.return_value = {"items": [{"id": "9"}], "meta": {"count": 1}}
    monkeypatch.setattr(mcp_server, "_ops", lambda: ops)
    out = mcp_server.kantata_link_post_to_task(post_id="9", story_id="55")
    assert "9" in out
    ops.update_post.assert_called_once_with(post_id="9", story_id="55")


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
        story_id=None,
    )
    assert "error" in out
    assert "/no/such/file" in out
