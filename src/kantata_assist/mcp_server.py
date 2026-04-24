"""Model Context Protocol (stdio) server exposing Kantata tools."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from kantata_assist.operations import operations_from_token

mcp = FastMCP(
    "kantata_assist",
    instructions="Tools for Kantata OX (Mavenlink): projects, tasks, time, activity, users.",
)


def _dump(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


def _ops():
    return operations_from_token()


@mcp.tool()
def kantata_whoami() -> str:
    """Return the current Kantata user (id, name, etc.)."""
    return _dump(_ops().whoami())


@mcp.tool()
def kantata_list_users(
    workspace_id: str | None = None,
    search: str | None = None,
    by_email_address: str | None = None,
    on_my_account: bool = False,
) -> str:
    """List Kantata users visible to your token (GET /users).

    Prefer workspace_id (participant_in) and/or search to limit size. by_email_address is an exact match.
    on_my_account lists account members (admin-oriented; may be large). Use ids from items[].id for assignees.
    """
    return _dump(
        _ops().list_users(
            workspace_id=workspace_id,
            search=search,
            by_email_address=by_email_address,
            on_my_account=on_my_account,
        )
    )


@mcp.tool()
def kantata_list_projects(search: str | None = None) -> str:
    """List workspaces (projects) you participate in. Optional search string."""
    return _dump(_ops().list_my_projects(search=search))


@mcp.tool()
def kantata_list_joinable_projects(search: str | None = None) -> str:
    """List workspaces visible to you where you are not yet a participant (best-effort heuristic)."""
    return _dump(_ops().list_joinable_projects(search=search))


@mcp.tool()
def kantata_join_project(workspace_id: str, role: str = "maven") -> str:
    """Add yourself to a workspace. role defaults to maven (consult Kantata docs for client vs maven)."""
    return _dump(_ops().join_project(workspace_id=workspace_id, role=role))


@mcp.tool()
def kantata_leave_project(workspace_id: str) -> str:
    """Remove yourself from a workspace (DELETE participation). May fail if you are team lead."""
    return _dump(_ops().leave_project(workspace_id=workspace_id))


@mcp.tool()
def kantata_list_tasks(
    workspace_id: str,
    parent_story_id: str | None = None,
    search: str | None = None,
) -> str:
    """List tasks (stories) for a workspace. Optionally filter by parent story or search text."""
    return _dump(
        _ops().list_tasks(
            workspace_id=workspace_id,
            parent_story_id=parent_story_id,
            search=search,
        )
    )


@mcp.tool()
def kantata_get_story(story_id: str) -> str:
    """Fetch a single story (task) by id."""
    return _dump(_ops().get_story(story_id=story_id))


@mcp.tool()
def kantata_create_task(
    workspace_id: str,
    title: str,
    description: str | None = None,
    parent_story_id: str | None = None,
    assign_me: bool = False,
    story_type: str | None = None,
) -> str:
    """Create a story. Set assign_me true to assign the current user.

    story_type: task (default if omitted), deliverable, milestone, or issue.
    """
    ops = _ops()
    assignees = [ops._current_user_id()] if assign_me else None
    return _dump(
        ops.upsert_task(
            workspace_id=workspace_id,
            title=title,
            description=description,
            parent_story_id=parent_story_id,
            assignee_user_ids=assignees,
            story_type=story_type,
        )
    )


@mcp.tool()
def kantata_update_task(
    story_id: str,
    title: str | None = None,
    description: str | None = None,
    parent_story_id: str | None = None,
    assign_me: bool = False,
    story_type: str | None = None,
) -> str:
    """Update a task. Provide at least one field to change; title defaults to existing if omitted.

    story_type: task, deliverable, milestone, or issue (Kantata story_type values).
    assign_me: if true, sets assignees to you only (replaces others). To add/remove without replacing,
    use kantata_adjust_task_assignees.
    """
    ops = _ops()
    t = title
    if t is None:
        t = str(ops.get_story(story_id=story_id)["story"].get("title") or "")
    assignees = [ops._current_user_id()] if assign_me else None
    return _dump(
        ops.upsert_task(
            workspace_id="",
            title=t,
            story_id=story_id,
            description=description,
            parent_story_id=parent_story_id,
            assignee_user_ids=assignees,
            story_type=story_type,
        )
    )


@mcp.tool()
def kantata_adjust_task_assignees(
    story_id: str,
    add_user_ids: str | None = None,
    remove_user_ids: str | None = None,
    add_me: bool = False,
    remove_me: bool = False,
    replace_assignee_user_ids: str | None = None,
) -> str:
    """Add or remove assignees without replacing everyone (unless you use replace_assignee_user_ids).

    add_user_ids / remove_user_ids: comma-separated Kantata user ids (resolve others via kantata_list_users).
    add_me / remove_me: add or remove the current user.
    replace_assignee_user_ids: comma-separated ids for the full assignee list (cannot mix with add/remove flags).
    """
    return _dump(
        _ops().adjust_story_assignees(
            story_id=story_id,
            add_user_ids=add_user_ids,
            remove_user_ids=remove_user_ids,
            add_me=add_me,
            remove_me=remove_me,
            replace_assignee_user_ids=replace_assignee_user_ids,
        )
    )


@mcp.tool()
def kantata_delete_task(story_id: str) -> str:
    """Soft-delete a task (story)."""
    return _dump(_ops().delete_task(story_id=story_id))


@mcp.tool()
def kantata_log_time(
    workspace_id: str,
    date_performed: str,
    time_in_minutes: int,
    story_id: str | None = None,
    notes: str | None = None,
) -> str:
    """Log time. date_performed is YYYY-MM-DD."""
    return _dump(
        _ops().log_time(
            workspace_id=workspace_id,
            date_performed=date_performed,
            time_in_minutes=time_in_minutes,
            story_id=story_id,
            notes=notes,
        )
    )


@mcp.tool()
def kantata_list_time_entries(
    workspace_id: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    with_user_ids: str | None = None,
    only_mine: bool = False,
    include: str | None = None,
) -> str:
    """List time entries visible to the token.

    Filters: workspace_id; date_start/date_end (YYYY-MM-DD, inclusive Kantata range).
    with_user_ids: comma-separated user ids. only_mine: current user only (not with with_user_ids).
    include: Kantata associations, e.g. user,story,workspace.
    """
    return _dump(
        _ops().list_time_entries(
            workspace_id=workspace_id,
            date_start=date_start,
            date_end=date_end,
            with_user_ids=with_user_ids,
            only_mine=only_mine,
            include=include,
        )
    )


@mcp.tool()
def kantata_delete_time_entry(time_entry_id: str) -> str:
    """Delete one time entry by id. Fails if locked, invoiced, or linked to a time adjustment."""
    return _dump(_ops().delete_time_entry(time_entry_id=time_entry_id))


@mcp.tool()
def kantata_submit_timesheet(workspace_id: str, start_date: str, end_date: str) -> str:
    """Submit a timesheet for one workspace. Dates are YYYY-MM-DD (Kantata may enforce pay-period rules)."""
    return _dump(
        _ops().submit_timesheet(
            workspace_id=workspace_id,
            start_date=start_date,
            end_date=end_date,
        )
    )


@mcp.tool()
def kantata_post_project_update(
    workspace_id: str,
    message: str,
    attachment_paths: list[str] | None = None,
    attachment_ids: list[str] | None = None,
) -> str:
    """Post to the project activity feed. Optional attachment_paths are local files the server can read."""
    try:
        return _dump(
            _ops().post_project_update(
                workspace_id=workspace_id,
                message=message,
                attachment_paths=attachment_paths,
                attachment_ids=attachment_ids,
            )
        )
    except FileNotFoundError as e:
        return _dump({"error": str(e)})


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
