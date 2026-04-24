"""High-level Kantata operations used by CLI and MCP."""

from __future__ import annotations

import mimetypes
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx

from kantata_assist.client import KantataAPIError, KantataClient
from kantata_assist.story_wbs import attach_schedule_wbs

# Kantata POST/PUT story.story_type enum (see Create / Update story API).
_STORY_TYPES = frozenset({"task", "deliverable", "milestone", "issue"})


def _coerce_story_type(value: str) -> str:
    s = str(value).strip().lower()
    if s not in _STORY_TYPES:
        allowed = ", ".join(sorted(_STORY_TYPES))
        raise ValueError(f"Invalid story_type {value!r}; use one of: {allowed}")
    return s


def _parse_csv_user_ids(value: str | None) -> list[str]:
    if value is None or not str(value).strip():
        return []
    return [p.strip() for p in str(value).split(",") if p.strip()]


def _meta(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {"count": payload.get("count")}


def _wrap_items(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {"items": KantataClient.items(payload), "meta": _meta(payload)}


def _paginate_all(client: KantataClient, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    params = dict(params or {})
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        p = {**params, "page": page, "per_page": 100}
        data = client.get(path, params=p)
        batch = KantataClient.items(data)
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return out


def _participations_index_requires_workspace_id(err: KantataAPIError) -> bool:
    """Some tenants reject GET /participations without workspace_id; use workspace listing fallback."""
    if err.status_code != 422:
        return False
    blob = (err.body or str(err)).lower()
    return "workspace_id" in blob


def _workspace_has_current_user_participation(w: Mapping[str, Any]) -> bool:
    """Kantata may return current_user_participation_id or current_user_participation_ids."""
    if w.get("current_user_participation_id"):
        return True
    ids = w.get("current_user_participation_ids")
    return isinstance(ids, list) and len(ids) > 0


def _sanitize_filename(name: str) -> str:
    base = Path(name).name
    base = re.sub(r"[^\w.\-]", "_", base)
    return base or "attachment"


class KantataOperations:
    def __init__(self, client: KantataClient) -> None:
        self._c = client

    def _current_user_id(self) -> str:
        u = self.whoami().get("user") or {}
        uid = u.get("id")
        if uid is None:
            raise RuntimeError("Could not resolve current user id from /users/me")
        return str(uid)

    def _participations_for_user(self, user_id: str) -> list[dict[str, Any]]:
        """List participations for a user; fails on tenants that require workspace_id on the index."""
        return _paginate_all(self._c, "/participations", {"user_id": user_id})

    def _list_my_projects_via_workspaces(self, *, search: str | None) -> dict[str, Any]:
        """Resolve 'my' workspaces when GET /participations?user_id= is not allowed."""
        params_ws: dict[str, Any] = {"include": "current_user_participation"}
        if search:
            params_ws["search"] = search
        all_ws = _paginate_all(self._c, "/workspaces", params_ws)
        mine = [w for w in all_ws if _workspace_has_current_user_participation(w)]
        if not mine:
            return {"items": [], "meta": {"count": 0}, "participations": []}
        ws_ids = sorted({str(w["id"]) for w in mine})
        params: dict[str, Any] = {"only": ",".join(ws_ids), "include": "participants"}
        if search:
            params["search"] = search
        data = self._c.get("/workspaces", params=params)
        return {**_wrap_items(data), "participations": []}

    def whoami(self) -> dict[str, Any]:
        data = self._c.get("/users/me")
        items = KantataClient.items(data)
        if items:
            return {"user": items[0]}
        if isinstance(data.get("id"), (str, int)):
            return {"user": data}
        return {"user": data}

    def list_users(
        self,
        *,
        workspace_id: str | None = None,
        search: str | None = None,
        by_email_address: str | None = None,
        on_my_account: bool = False,
    ) -> dict[str, Any]:
        """List users visible to the token (GET /users). Prefer workspace_id or search to keep results small.

        See Kantata GET /users: participant_in (workspace), search, by_email_address, on_my_account, etc.
        """
        if not workspace_id and not search and not by_email_address and not on_my_account:
            raise ValueError(
                "Provide at least one of workspace_id, search, by_email_address, or on_my_account"
            )
        params: dict[str, Any] = {}
        if workspace_id:
            params["participant_in"] = int(workspace_id)
        if search:
            params["search"] = search
        if by_email_address:
            params["by_email_address"] = by_email_address.strip()
        if on_my_account:
            params["on_my_account"] = "true"
        items = _paginate_all(self._c, "/users", params if params else None)
        return {"items": items, "meta": {"count": len(items)}}

    def list_my_projects(self, *, search: str | None = None) -> dict[str, Any]:
        uid = self._current_user_id()
        try:
            parts = self._participations_for_user(uid)
        except KantataAPIError as e:
            if _participations_index_requires_workspace_id(e):
                return self._list_my_projects_via_workspaces(search=search)
            raise
        ws_ids = sorted({str(p.get("workspace_id")) for p in parts if p.get("workspace_id") is not None})
        if not ws_ids:
            return {"items": [], "meta": {"count": 0}, "participations": parts}
        params: dict[str, Any] = {"only": ",".join(ws_ids), "include": "participants"}
        if search:
            params["search"] = search
        data = self._c.get("/workspaces", params=params)
        return {**_wrap_items(data), "participations": parts}

    def list_joinable_projects(self, *, search: str | None = None) -> dict[str, Any]:
        uid = self._current_user_id()
        try:
            parts = self._participations_for_user(uid)
        except KantataAPIError as e:
            if not _participations_index_requires_workspace_id(e):
                raise
            params_ws: dict[str, Any] = {"include": "current_user_participation"}
            if search:
                params_ws["search"] = search
            candidates = _paginate_all(self._c, "/workspaces", params_ws)
            joinable = [w for w in candidates if not _workspace_has_current_user_participation(w)]
            return {"items": joinable, "meta": {"count": len(joinable)}}
        participated = {str(p.get("workspace_id")) for p in parts if p.get("workspace_id")}
        params: dict[str, Any] = {}
        if search:
            params["search"] = search
        candidates = _paginate_all(self._c, "/workspaces", params)
        joinable = [w for w in candidates if str(w.get("id")) not in participated]
        return {"items": joinable, "meta": {"count": len(joinable)}}

    def join_project(self, *, workspace_id: str, role: str = "maven") -> dict[str, Any]:
        uid = self._current_user_id()
        body = {"participations": [{"workspace_id": int(workspace_id), "user_id": int(uid), "role": role}]}
        data = self._c.post("/participations", json_body=body)
        return _wrap_items(data)

    def leave_project(self, *, workspace_id: str) -> dict[str, Any]:
        """Remove the current user from a workspace (DELETE their participation)."""
        uid = self._current_user_id()
        rows: list[dict[str, Any]] = []
        try:
            rows = _paginate_all(
                self._c,
                "/participations",
                {"workspace_id": int(workspace_id), "user_id": int(uid)},
            )
        except KantataAPIError:
            rows = _paginate_all(self._c, "/participations", {"workspace_id": int(workspace_id)})
            rows = [p for p in rows if str(p.get("user_id")) == uid]
        mine = [
            p
            for p in rows
            if str(p.get("workspace_id")) == str(workspace_id) and str(p.get("user_id")) == uid
        ]
        if not mine:
            raise RuntimeError(f"No participation found for you on workspace {workspace_id}")
        pid = mine[0].get("id")
        if pid is None:
            raise RuntimeError(f"Participation has no id: {mine[0]!r}")
        self._c.delete(f"/participations/{pid}")
        return {"ok": True, "workspace_id": workspace_id, "participation_id": str(pid)}

    def get_story(self, *, story_id: str, include: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if include:
            params["include"] = include
        data = self._c.get(f"/stories/{story_id}", params=params or None)
        items = KantataClient.items(data)
        if items:
            return {"story": items[0]}
        return {"story": data}

    def list_tasks(
        self,
        *,
        workspace_id: str,
        parent_story_id: str | None = None,
        search: str | None = None,
        include_wbs: bool = True,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"workspace_id": workspace_id, "include": "assignees"}
        if parent_story_id:
            params["parent_story_id"] = parent_story_id
        if search:
            params["search"] = search
        items = _paginate_all(self._c, "/stories", params)
        meta: dict[str, Any] = {"count": len(items)}
        if include_wbs:
            attach_schedule_wbs(items)
            meta["wbs"] = (
                "client-computed from parent_id + position; matches Kantata schedule "
                "when this payload includes all stories for the workspace."
            )
        return {"items": items, "meta": meta}

    def upsert_task(
        self,
        *,
        workspace_id: str,
        title: str,
        story_id: str | None = None,
        description: str | None = None,
        parent_story_id: str | None = None,
        assignee_user_ids: list[str] | None = None,
        story_type: str | None = None,
    ) -> dict[str, Any]:
        assignee_user_ids = assignee_user_ids or []
        assignments = [{"assignee_id": int(x)} for x in assignee_user_ids if str(x).strip()]
        if story_id:
            patch: dict[str, Any] = {}
            if title is not None and str(title).strip():
                patch["title"] = title
            if description is not None:
                patch["description"] = description
            if parent_story_id is not None:
                patch["parent_id"] = int(parent_story_id)
            if assignments:
                patch["assignments"] = assignments
            if story_type is not None:
                patch["story_type"] = _coerce_story_type(story_type)
            if not patch:
                raise ValueError(
                    "update requires at least one of title, description, parent_id, assignees, story_type"
                )
            body = {"story": patch}
            data = self._c.put(f"/stories/{story_id}", json_body=body)
        else:
            story: dict[str, Any] = {
                "workspace_id": int(workspace_id),
                "title": title,
            }
            if description is not None:
                story["description"] = description
            if parent_story_id:
                story["parent_id"] = int(parent_story_id)
            if story_type is not None:
                story["story_type"] = _coerce_story_type(story_type)
            if assignments:
                story["assignments"] = assignments
            body = {"stories": [story]}
            data = self._c.post("/stories", json_body=body)
        return _wrap_items(data)

    def adjust_story_assignees(
        self,
        *,
        story_id: str,
        add_user_ids: str | None = None,
        remove_user_ids: str | None = None,
        add_me: bool = False,
        remove_me: bool = False,
        replace_assignee_user_ids: str | None = None,
    ) -> dict[str, Any]:
        """Set story assignees via PUT assignments: replace entire set, or merge add/remove (+ add_me/remove_me).

        replace_assignee_user_ids: comma-separated Kantata user ids (exclusive with other assignee options).
        """
        has_replace = replace_assignee_user_ids is not None
        has_merge = bool(
            _parse_csv_user_ids(add_user_ids)
            or _parse_csv_user_ids(remove_user_ids)
            or add_me
            or remove_me
        )
        if has_replace and has_merge:
            raise ValueError(
                "replace_assignee_user_ids cannot be combined with add_user_ids, remove_user_ids, add_me, or remove_me"
            )
        if not has_replace and not has_merge:
            raise ValueError(
                "Provide replace_assignee_user_ids and/or add_user_ids, remove_user_ids, add_me, or remove_me"
            )

        if has_replace:
            final_ids = _parse_csv_user_ids(replace_assignee_user_ids)
        else:
            row = self.get_story(story_id=story_id, include="assignees")["story"]
            raw = row.get("assignee_ids")
            current: set[str] = set()
            if isinstance(raw, list):
                current = {str(x) for x in raw}
            for uid in _parse_csv_user_ids(add_user_ids):
                current.add(str(uid))
            if add_me:
                current.add(self._current_user_id())
            for uid in _parse_csv_user_ids(remove_user_ids):
                current.discard(str(uid))
            if remove_me:
                current.discard(self._current_user_id())
            final_ids = sorted(current, key=lambda x: int(x))

        assignments = [{"assignee_id": int(x)} for x in final_ids if str(x).strip()]
        body = {"story": {"assignments": assignments}}
        data = self._c.put(f"/stories/{story_id}", json_body=body)
        return _wrap_items(data)

    def delete_task(self, *, story_id: str) -> dict[str, Any]:
        self._c.delete(f"/stories/{story_id}")
        return {"ok": True, "story_id": story_id}

    def log_time(
        self,
        *,
        workspace_id: str,
        date_performed: str,
        time_in_minutes: int,
        story_id: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        row: dict[str, Any] = {
            "workspace_id": int(workspace_id),
            "date_performed": date_performed,
            "time_in_minutes": int(time_in_minutes),
        }
        if story_id:
            row["story_id"] = int(story_id)
        if notes is not None:
            row["notes"] = notes
        data = self._c.post("/time_entries", json_body={"time_entries": [row]})
        return _wrap_items(data)

    def list_time_entries(
        self,
        *,
        workspace_id: str | None = None,
        date_start: str | None = None,
        date_end: str | None = None,
        with_user_ids: str | None = None,
        only_mine: bool = False,
        include: str | None = None,
    ) -> dict[str, Any]:
        """List time entries (GET /time_entries) with optional filters. Paginates until exhausted."""
        if only_mine and with_user_ids:
            raise ValueError("Use only one of only_mine and with_user_ids")
        params: dict[str, Any] = {}
        if workspace_id:
            params["workspace_id"] = int(workspace_id)
        if date_start or date_end:
            start = date_start or date_end
            end = date_end or date_start
            if not start or not end:
                raise ValueError("date_start and date_end (or a single date in both) are required for date filtering")
            params["date_performed_between"] = f"{start}:{end}"
        if only_mine:
            params["with_user_ids"] = self._current_user_id()
        elif with_user_ids:
            params["with_user_ids"] = with_user_ids
        if include:
            params["include"] = include
        items = _paginate_all(self._c, "/time_entries", params)
        return {"items": items, "meta": {"count": len(items)}}

    def delete_time_entry(self, *, time_entry_id: str) -> dict[str, Any]:
        """Delete a time entry (DELETE /time_entries/{id}). Kantata may reject locked/invoiced/adjusted rows."""
        self._c.delete(f"/time_entries/{time_entry_id}")
        return {"ok": True, "time_entry_id": time_entry_id}

    def submit_timesheet(
        self,
        *,
        workspace_id: str,
        start_date: str,
        end_date: str,
        extra: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        row: dict[str, Any] = {
            "workspace_id": int(workspace_id),
            "start_date": start_date,
            "end_date": end_date,
        }
        if extra:
            row.update(dict(extra))
        data = self._c.post("/timesheet_submissions", json_body={"timesheet_submissions": [row]})
        return _wrap_items(data)

    def _upload_post_attachment_server(self, path: Path) -> str:
        raw = path.read_bytes()
        fname = _sanitize_filename(path.name)
        ctype = mimetypes.guess_type(fname)[0] or "application/octet-stream"
        files = {"attachment[data]": (fname, raw, ctype)}
        data = {"attachment[type]": "post_attachment"}
        payload = self._c.post("/attachments", data=data, files=files)
        items = KantataClient.items(payload)
        if items:
            return str(items[0]["id"])
        if payload.get("id") is not None:
            return str(payload["id"])
        raise RuntimeError(f"Unexpected attachment response: {payload!r}")

    def _upload_post_attachment_cdn(self, path: Path) -> str:
        fname = _sanitize_filename(path.name)
        create = self._c.post(
            "/attachments",
            data={
                "direct": "true",
                "attachment[filename]": fname,
                "attachment[type]": "post_attachment",
            },
        )
        aid = create.get("id")
        if aid is None:
            items = KantataClient.items(create)
            if items and items[0].get("id") is not None:
                aid = items[0]["id"]
        if aid is None:
            raise RuntimeError(f"No attachment id in CDN init: {create!r}")
        aid_s = str(aid)
        action = create.get("action")
        fields = create.get("fields")
        if not isinstance(action, str) or not isinstance(fields, dict):
            raise RuntimeError(f"Missing CDN upload action/fields: {create!r}")
        raw = path.read_bytes()
        ctype = mimetypes.guess_type(fname)[0] or "application/octet-stream"
        form = {k: str(v) for k, v in fields.items()}
        with httpx.Client(timeout=120.0, follow_redirects=True) as hx:
            r = hx.post(action, data=form, files={"file": (fname, raw, ctype)})
            r.raise_for_status()
        self._c.put(f"/attachments/{aid_s}/sync")
        return aid_s

    def _upload_post_attachment_auto(self, path: Path) -> str:
        size = path.stat().st_size
        if size <= 9 * 1024 * 1024:
            return self._upload_post_attachment_server(path)
        return self._upload_post_attachment_cdn(path)

    def post_project_update(
        self,
        *,
        workspace_id: str,
        message: str,
        attachment_paths: list[str] | None = None,
        attachment_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        ids: list[str] = list(attachment_ids or [])
        for p in attachment_paths or []:
            pp = Path(p).expanduser()
            if not pp.is_file():
                raise FileNotFoundError(f"Not a file: {pp}")
            ids.append(self._upload_post_attachment_auto(pp))
        post: dict[str, Any] = {
            "workspace_id": int(workspace_id),
            "message": message,
        }
        if ids:
            post["attachment_ids"] = [int(x) for x in ids]
        data = self._c.post("/posts", json_body={"posts": [post]})
        return _wrap_items(data)


def operations_from_token(
    access_token: str | None = None, *, api_base: str | None = None
) -> KantataOperations:
    from kantata_assist.config import load_access_token, load_api_base

    token = access_token or load_access_token()
    base = api_base if api_base is not None else load_api_base()
    client = KantataClient(token, api_base=base)
    return KantataOperations(client)
