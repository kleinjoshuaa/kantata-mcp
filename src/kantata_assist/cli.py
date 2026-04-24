"""Typer CLI for Kantata Assist."""

from __future__ import annotations

import json
import sys
from typing import Annotated, Any

import typer

from kantata_assist.client import KantataAPIError
from kantata_assist.oauth import login_interactive
from kantata_assist.operations import operations_from_token

app = typer.Typer(
    name="kantata",
    help="Kantata OX (Mavenlink) API — projects, tasks, time, activity feed.",
    no_args_is_help=True,
)


def _json(data: Any) -> None:
    typer.echo(json.dumps(data, indent=2, default=str))


@app.command()
def login(
    port: Annotated[
        int | None,
        typer.Option("--port", help="OAuth callback port (default 8765; must match Kantata redirect URI)"),
    ] = None,
    no_browser: Annotated[bool, typer.Option("--no-browser")] = False,
) -> None:
    """OAuth2 login: opens browser, saves access token to credentials file."""
    login_interactive(redirect_port=port, open_browser=not no_browser)


@app.command("whoami")
def cmd_whoami() -> None:
    """Print current Kantata user."""
    _json(operations_from_token().whoami())


@app.command("list-users")
def cmd_list_users(
    workspace: Annotated[str | None, typer.Option("--workspace", help="Only users in this workspace id")] = None,
    search: Annotated[str | None, typer.Option("--search")] = None,
    email: Annotated[str | None, typer.Option("--email", help="Exact email match (Kantata by_email_address)")] = None,
    on_my_account: Annotated[
        bool,
        typer.Option("--on-my-account", help="All users on your account (can be large)"),
    ] = False,
) -> None:
    """List users visible to your token; use for assignee ids (GET /users)."""
    if not workspace and not search and not email and not on_my_account:
        typer.echo("Provide at least one of --workspace, --search, --email, or --on-my-account", err=True)
        raise typer.Exit(1)
    _json(
        operations_from_token().list_users(
            workspace_id=workspace,
            search=search,
            by_email_address=email,
            on_my_account=on_my_account,
        )
    )


@app.command("list-projects")
def cmd_list_projects(
    search: Annotated[str | None, typer.Option("--search")] = None,
) -> None:
    """List workspaces you participate in."""
    _json(operations_from_token().list_my_projects(search=search))


@app.command("list-joinable")
def cmd_list_joinable(
    search: Annotated[str | None, typer.Option("--search")] = None,
) -> None:
    """List workspaces visible to you that you are not participating in."""
    _json(operations_from_token().list_joinable_projects(search=search))


@app.command("join-project")
def cmd_join(
    workspace_id: str,
    role: Annotated[str, typer.Option("--role")] = "maven",
) -> None:
    """Add yourself as a participant on a workspace."""
    _json(operations_from_token().join_project(workspace_id=workspace_id, role=role))


@app.command("leave-project")
def cmd_leave(workspace_id: str) -> None:
    """Remove yourself from a workspace (delete your participation)."""
    _json(operations_from_token().leave_project(workspace_id=workspace_id))


@app.command("list-tasks")
def cmd_list_tasks(
    workspace_id: str,
    parent: Annotated[str | None, typer.Option("--parent")] = None,
    search: Annotated[str | None, typer.Option("--search")] = None,
) -> None:
    """List stories (tasks) for a workspace."""
    _json(
        operations_from_token().list_tasks(
            workspace_id=workspace_id,
            parent_story_id=parent,
            search=search,
        )
    )


@app.command("create-task")
def cmd_create_task(
    workspace_id: str,
    title: str,
    description: Annotated[str | None, typer.Option("--description")] = None,
    parent: Annotated[str | None, typer.Option("--parent")] = None,
    assign_me: Annotated[bool, typer.Option("--assign-me")] = False,
    story_type: Annotated[
        str | None,
        typer.Option(
            "--story-type",
            help="task | deliverable | milestone | issue (Kantata story types)",
        ),
    ] = None,
) -> None:
    """Create a story (task, deliverable, milestone, or issue)."""
    ops = operations_from_token()
    assignees: list[str] | None = None
    if assign_me:
        assignees = [ops._current_user_id()]
    _json(
        ops.upsert_task(
            workspace_id=workspace_id,
            title=title,
            description=description,
            parent_story_id=parent,
            assignee_user_ids=assignees,
            story_type=story_type,
        )
    )


@app.command("update-task")
def cmd_update_task(
    story_id: str,
    title: Annotated[str | None, typer.Option("--title")] = None,
    description: Annotated[str | None, typer.Option("--description")] = None,
    parent: Annotated[str | None, typer.Option("--parent")] = None,
    assign_me: Annotated[bool, typer.Option("--assign-me")] = False,
    story_type: Annotated[
        str | None,
        typer.Option(
            "--story-type",
            help="task | deliverable | milestone | issue (Kantata story types)",
        ),
    ] = None,
) -> None:
    """Update a story. At least one of --title / --description / --parent / --assign-me / --story-type."""
    ops = operations_from_token()
    if title is None and description is None and parent is None and not assign_me and story_type is None:
        typer.echo(
            "Provide --title, --description, --parent, --assign-me, and/or --story-type",
            err=True,
        )
        raise typer.Exit(1)
    t = title
    if t is None:
        t = str(ops.get_story(story_id=story_id)["story"].get("title") or "")
    assignees: list[str] | None = None
    if assign_me:
        assignees = [ops._current_user_id()]
    _json(
        ops.upsert_task(
            workspace_id="",
            title=t,
            story_id=story_id,
            description=description,
            parent_story_id=parent,
            assignee_user_ids=assignees,
            story_type=story_type,
        )
    )


@app.command("adjust-assignees")
def cmd_adjust_assignees(
    story_id: str,
    add: Annotated[str | None, typer.Option("--add", help="Comma-separated user ids to add")] = None,
    remove: Annotated[str | None, typer.Option("--remove", help="Comma-separated user ids to remove")] = None,
    add_me: Annotated[bool, typer.Option("--add-me", help="Add current user to assignees")] = False,
    remove_me: Annotated[bool, typer.Option("--remove-me", help="Remove current user from assignees")] = False,
    replace: Annotated[
        str | None,
        typer.Option("--replace", help="Comma-separated ids; full assignee list (exclusive with other flags)"),
    ] = None,
) -> None:
    """Add/remove assignees, or replace the full assignee list. Use instead of --assign-me when preserving others."""
    if not replace and not add and not remove and not add_me and not remove_me:
        typer.echo("Provide --add, --remove, --add-me, --remove-me, and/or --replace", err=True)
        raise typer.Exit(1)
    _json(
        operations_from_token().adjust_story_assignees(
            story_id=story_id,
            add_user_ids=add,
            remove_user_ids=remove,
            add_me=add_me,
            remove_me=remove_me,
            replace_assignee_user_ids=replace,
        )
    )


@app.command("delete-task")
def cmd_delete_task(story_id: str) -> None:
    """Soft-delete a story."""
    _json(operations_from_token().delete_task(story_id=story_id))


@app.command("log-time")
def cmd_log_time(
    workspace_id: str,
    date: str,
    minutes: int,
    story_id: Annotated[str | None, typer.Option("--story")] = None,
    notes: Annotated[str | None, typer.Option("--notes")] = None,
) -> None:
    """Create a time entry (date: YYYY-MM-DD)."""
    _json(
        operations_from_token().log_time(
            workspace_id=workspace_id,
            date_performed=date,
            time_in_minutes=minutes,
            story_id=story_id,
            notes=notes,
        )
    )


@app.command("list-time-entries")
def cmd_list_time_entries(
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    date_from: Annotated[str | None, typer.Option("--from", help="YYYY-MM-DD (inclusive)")] = None,
    date_to: Annotated[str | None, typer.Option("--to", help="YYYY-MM-DD (inclusive)")] = None,
    with_user_ids: Annotated[str | None, typer.Option("--user-ids", help="Comma-separated Kantata user ids")] = None,
    only_mine: Annotated[bool, typer.Option("--only-mine", help="Restrict to current user")] = False,
    include: Annotated[str | None, typer.Option("--include", help="Kantata include= associations")] = None,
) -> None:
    """List time entries (optionally filter by workspace, date range, user)."""
    _json(
        operations_from_token().list_time_entries(
            workspace_id=workspace,
            date_start=date_from,
            date_end=date_to,
            with_user_ids=with_user_ids,
            only_mine=only_mine,
            include=include,
        )
    )


@app.command("delete-time-entry")
def cmd_delete_time_entry(time_entry_id: str) -> None:
    """Delete a time entry by id (Kantata may reject locked/invoiced entries)."""
    _json(operations_from_token().delete_time_entry(time_entry_id=time_entry_id))


@app.command("submit-timesheet")
def cmd_submit_timesheet(
    workspace_id: str,
    start: str,
    end: str,
) -> None:
    """Submit a timesheet for a workspace (dates: YYYY-MM-DD)."""
    _json(
        operations_from_token().submit_timesheet(
            workspace_id=workspace_id,
            start_date=start,
            end_date=end,
        )
    )


@app.command("post-update")
def cmd_post_update(
    workspace_id: str,
    message: str,
    attach: Annotated[str | None, typer.Option("--attach", help="Comma-separated local file paths")] = None,
) -> None:
    """Post to project activity; use --attach with comma-separated file paths."""
    paths = [p.strip() for p in attach.split(",") if p.strip()] if attach else None
    _json(
        operations_from_token().post_project_update(
            workspace_id=workspace_id,
            message=message,
            attachment_paths=paths,
        )
    )


def main() -> None:
    try:
        app()
    except KantataAPIError as e:
        typer.echo(str(e), err=True)
        if e.body:
            typer.echo(e.body, err=True)
        sys.exit(1)
    except RuntimeError as e:
        typer.echo(str(e), err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
