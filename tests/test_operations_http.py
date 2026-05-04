"""KantataOperations integration-style tests against MockTransport."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from kantata_assist.client import KantataAPIError, KantataClient
from kantata_assist.operations import _paginate_all, _participations_index_requires_workspace_id
from tests.conftest import operations_with_transport


def test_whoami_from_results_shape() -> None:
    payload = {
        "count": 1,
        "results": [{"key": "users", "id": "9"}],
        "users": {"9": {"id": "9", "full_name": "Pat"}},
    }

    def h(request: httpx.Request) -> httpx.Response:
        assert "/users/me.json" in request.url.path
        return httpx.Response(200, json=payload)

    ops = operations_with_transport(h)
    u = ops.whoami()["user"]
    assert u["id"] == "9"
    assert u["full_name"] == "Pat"


def test_whoami_plain_object_without_results() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "1", "full_name": "Solo"})

    ops = operations_with_transport(h)
    assert ops.whoami()["user"]["id"] == "1"


def test_list_users_participant_filter() -> None:
    calls: list[str] = []

    def h(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        assert "participant_in=55" in str(request.url)
        return httpx.Response(
            200,
            json={
                "count": 1,
                "results": [{"key": "users", "id": "1"}],
                "users": {"1": {"id": "1", "email_address": "a@b.c"}},
            },
        )

    ops = operations_with_transport(h)
    r = ops.list_users(workspace_id="55", search=None, by_email_address=None, on_my_account=False)
    assert len(r["items"]) == 1
    assert r["items"][0]["id"] == "1"


def test_get_story_with_include() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        assert "include=assignees" in str(request.url)
        return httpx.Response(
            200,
            json={
                "count": 1,
                "results": [{"key": "stories", "id": "10"}],
                "stories": {"10": {"id": "10", "assignee_ids": ["1", "2"]}},
            },
        )

    ops = operations_with_transport(h)
    s = ops.get_story(story_id="10", include="assignees")["story"]
    assert s["assignee_ids"] == ["1", "2"]


def test_adjust_story_assignees_merge() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and "/stories/10.json" in request.url.path:
            assert "include=assignees" in str(request.url)
            return httpx.Response(
                200,
                json={
                    "count": 1,
                    "results": [{"key": "stories", "id": "10"}],
                    "stories": {"10": {"id": "10", "assignee_ids": ["99"]}},
                },
            )
        if request.method == "PUT" and "/stories/10.json" in request.url.path:
            body = json.loads(request.content.decode())
            assigns = body["story"]["assignments"]
            ids = sorted(a["assignee_id"] for a in assigns)
            assert ids == [42, 99]
            return httpx.Response(
                200,
                json={
                    "count": 1,
                    "results": [{"key": "stories", "id": "10"}],
                    "stories": {"10": {"id": "10", "assignee_ids": [str(i) for i in ids]}},
                },
            )
        raise AssertionError(request.url)

    ops = operations_with_transport(h)
    with patch.object(ops, "whoami", return_value={"user": {"id": "42"}}):
        r = ops.adjust_story_assignees(
            story_id="10",
            add_user_ids=None,
            remove_user_ids=None,
            add_me=True,
            remove_me=False,
            replace_assignee_user_ids=None,
        )
    assert r["items"][0]["id"] == "10"


def test_adjust_story_assignees_replace() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        body = json.loads(request.content.decode())
        assert [a["assignee_id"] for a in body["story"]["assignments"]] == [7, 8]
        return httpx.Response(
            200,
            json={
                "count": 1,
                "results": [{"key": "stories", "id": "1"}],
                "stories": {"1": {"id": "1"}},
            },
        )

    ops = operations_with_transport(h)
    ops.adjust_story_assignees(
        story_id="1",
        replace_assignee_user_ids="7,8",
    )


def test_create_task_post() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        body = json.loads(request.content.decode())
        assert body["stories"][0]["title"] == "Hello"
        assert body["stories"][0]["workspace_id"] == 3
        return httpx.Response(
            200,
            json={
                "count": 1,
                "results": [{"key": "stories", "id": "5"}],
                "stories": {"5": {"id": "5", "title": "Hello"}},
            },
        )

    ops = operations_with_transport(h)
    r = ops.upsert_task(workspace_id="3", title="Hello")
    assert r["items"][0]["title"] == "Hello"


def test_update_task_put() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert body["story"]["title"] == "New"
        return httpx.Response(
            200,
            json={
                "count": 1,
                "results": [{"key": "stories", "id": "5"}],
                "stories": {"5": {"id": "5", "title": "New"}},
            },
        )

    ops = operations_with_transport(h)
    ops.upsert_task(workspace_id="", title="New", story_id="5")


def test_update_task_status_put() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.path.endswith("/stories/5.json")
        body = json.loads(request.content.decode())
        assert body == {"story": {"status": "Completed"}}
        return httpx.Response(
            200,
            json={
                "count": 1,
                "results": [{"key": "stories", "id": "5"}],
                "stories": {"5": {"id": "5", "status": "Completed"}},
            },
        )

    ops = operations_with_transport(h)
    ops.upsert_task(workspace_id="", title="", story_id="5", status="Completed")


def test_delete_task() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        return httpx.Response(204)

    ops = operations_with_transport(h)
    assert ops.delete_task(story_id="9") == {"ok": True, "story_id": "9"}


def test_list_tasks_single_page() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        assert "workspace_id=1" in str(request.url)
        return httpx.Response(
            200,
            json={
                "count": 1,
                "results": [{"key": "stories", "id": "1"}],
                "stories": {"1": {"id": "1", "title": "A"}},
            },
        )

    ops = operations_with_transport(h)
    r = ops.list_tasks(workspace_id="1")
    assert len(r["items"]) == 1
    assert r["items"][0]["wbs"] == "1"
    assert "wbs" in r["meta"] and isinstance(r["meta"]["wbs"], str)

    r2 = ops.list_tasks(workspace_id="1", include_wbs=False)
    assert "wbs" not in r2["items"][0]


def test_create_time_off_entries_bulk() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "/time_off_entries.json" in request.url.path:
            body = json.loads(request.content.decode())
            assert body["time_off_entries"] == [
                {"user_id": 99, "hours": 8.0, "requested_date": "2026-04-20"},
                {"user_id": 99, "hours": 8.0, "requested_date": "2026-04-21"},
            ]
            return httpx.Response(
                200,
                json={
                    "count": 2,
                    "results": [{"key": "time_off_entries", "id": "1"}, {"key": "time_off_entries", "id": "2"}],
                    "time_off_entries": {"1": {"id": "1"}, "2": {"id": "2"}},
                },
            )
        raise AssertionError(request.url)

    ops = operations_with_transport(h)
    r = ops.create_time_off_entries(
        requested_dates=["2026-04-20", "2026-04-21"],
        hours=8,
        user_id="99",
    )
    assert r["meta"]["count"] == 2


def test_create_time_off_entries_defaults_user() -> None:
    n = {"body": None}

    def h(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "/time_off_entries.json" in request.url.path:
            n["body"] = json.loads(request.content.decode())
            return httpx.Response(
                200,
                json={"count": 1, "results": [{"key": "time_off_entries", "id": "1"}], "time_off_entries": {"1": {"id": "1"}}},  # noqa: E501
            )
        if request.method == "GET" and "/users/me.json" in request.url.path:
            return httpx.Response(200, json={"id": "7", "full_name": "Me"})
        raise AssertionError(request.url)

    ops = operations_with_transport(h)
    ops.create_time_off_entries(requested_dates=["2026-05-01"], hours=4, user_id=None)
    assert n["body"]["time_off_entries"][0]["user_id"] == 7


def test_create_time_off_entries_requires_dates() -> None:
    ops = operations_with_transport(lambda r: httpx.Response(500))
    with pytest.raises(ValueError, match="at least one"):
        ops.create_time_off_entries(requested_dates=[], hours=8)


def test_list_time_off_entries() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and "/time_off_entries.json" in request.url.path:
            assert "start_date=2026-04-01" in str(request.url)
            assert "user_id=5" in str(request.url)
            return httpx.Response(
                200,
                json={"count": 1, "results": [{"key": "time_off_entries", "id": "1"}], "time_off_entries": {"1": {"id": "1"}}},  # noqa: E501
            )
        raise AssertionError(request.url)

    ops = operations_with_transport(h)
    r = ops.list_time_off_entries(start_date="2026-04-01", user_id="5")
    assert r["meta"]["count"] == 1


def test_list_time_off_entries_only_mine_conflict() -> None:
    ops = operations_with_transport(lambda r: httpx.Response(500))
    with pytest.raises(ValueError, match="only one"):
        ops.list_time_off_entries(only_mine=True, user_id="1")


def test_log_time_and_delete_time_entry() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "/time_entries.json" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "count": 1,
                    "results": [{"key": "time_entries", "id": "88"}],
                    "time_entries": {"88": {"id": "88"}},
                },
            )
        if request.method == "DELETE":
            return httpx.Response(204)
        raise AssertionError(request.url)

    ops = operations_with_transport(h)
    r = ops.log_time(workspace_id="1", date_performed="2026-01-01", time_in_minutes=30)
    assert r["items"][0]["id"] == "88"
    assert ops.delete_time_entry(time_entry_id="88")["ok"] is True


def test_update_time_entry() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT" and request.url.path.endswith("/time_entries/88.json"):
            body = json.loads(request.content.decode())
            assert body == {"time_entry": {"notes": "test note", "time_in_minutes": 60}}
            return httpx.Response(
                200,
                json={
                    "count": 1,
                    "results": [{"key": "time_entries", "id": "88"}],
                    "time_entries": {"88": {"id": "88", "notes": "test note", "time_in_minutes": 60}},
                },
            )
        raise AssertionError(request.url)

    ops = operations_with_transport(h)
    r = ops.update_time_entry(time_entry_id="88", notes="test note", time_in_minutes=60)
    assert r["items"][0]["id"] == "88"
    assert r["items"][0]["notes"] == "test note"


def test_update_time_entry_requires_field() -> None:
    ops = operations_with_transport(lambda r: httpx.Response(500))
    with pytest.raises(ValueError, match="Provide at least one"):
        ops.update_time_entry(time_entry_id="88")


def test_list_time_entries_paginates() -> None:
    n = {"call": 0}

    def h(request: httpx.Request) -> httpx.Response:
        n["call"] += 1
        if n["call"] == 1:
            return httpx.Response(
                200,
                json={
                    "count": 150,
                    "results": [{"key": "time_entries", "id": str(i)} for i in range(100)],
                    "time_entries": {str(i): {"id": str(i)} for i in range(100)},
                },
            )
        return httpx.Response(
            200,
            json={
                "count": 150,
                "results": [{"key": "time_entries", "id": "50"}],
                "time_entries": {"50": {"id": "50"}},
            },
        )

    ops = operations_with_transport(h)
    r = ops.list_time_entries(date_start="2026-01-01", date_end="2026-01-31")
    assert r["meta"]["count"] == 101


def test_submit_timesheet() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert "timesheet_submissions" in body
        return httpx.Response(
            200,
            json={"count": 0, "results": [], "timesheet_submissions": {}},
        )

    ops = operations_with_transport(h)
    ops.submit_timesheet(workspace_id="1", start_date="2026-01-01", end_date="2026-01-07")


def test_post_project_update_no_attachments() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert body["posts"][0]["message"] == "Hi"
        assert body["posts"][0]["workspace_id"] == 1
        assert "recipient_ids" not in body["posts"][0]
        return httpx.Response(
            200,
            json={"count": 1, "results": [{"key": "posts", "id": "1"}], "posts": {"1": {"id": "1"}}},
        )

    ops = operations_with_transport(h)
    ops.post_project_update(workspace_id="1", message="Hi")


def test_post_project_update_story_id() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert body["posts"][0]["message"] == "Hi"
        assert body["posts"][0]["story_id"] == 55
        return httpx.Response(
            200,
            json={"count": 1, "results": [{"key": "posts", "id": "1"}], "posts": {"1": {"id": "1"}}},
        )

    ops = operations_with_transport(h)
    ops.post_project_update(workspace_id="1", message="Hi", story_id="55")


def test_post_project_update_recipient_user_ids() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert body["posts"][0]["recipient_ids"] == [2, 3]
        return httpx.Response(
            200,
            json={"count": 1, "results": [{"key": "posts", "id": "1"}], "posts": {"1": {"id": "1"}}},
        )

    ops = operations_with_transport(h)
    ops.post_project_update(
        workspace_id="1",
        message="Hi",
        recipient_user_ids=["2", "3"],
    )


def test_post_project_update_recipient_emails_resolved() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and "/users.json" in request.url.path:
            assert "participant_in=1" in str(request.url).replace("%2C", ",")
            return httpx.Response(
                200,
                json={
                    "count": 1,
                    "results": [{"key": "users", "id": "9"}],
                    "users": {"9": {"id": "9", "email_address": "nobody@example.com"}},
                },
            )
        if request.method == "POST" and "/posts.json" in request.url.path:
            body = json.loads(request.content.decode())
            assert body["posts"][0]["recipient_ids"] == [2, 9]
            return httpx.Response(
                200,
                json={"count": 1, "results": [{"key": "posts", "id": "1"}], "posts": {"1": {"id": "1"}}},
            )
        raise AssertionError(request.url)

    ops = operations_with_transport(h)
    ops.post_project_update(
        workspace_id="1",
        message="Hi",
        recipient_user_ids=["2"],
        recipient_emails=["nobody@example.com"],
    )


def test_post_project_update_recipient_email_not_found() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and "/users.json" in request.url.path:
            return httpx.Response(200, json={"count": 0, "results": [], "users": {}})
        raise AssertionError(request.url)

    ops = operations_with_transport(h)
    with pytest.raises(ValueError, match="No Kantata user with email"):
        ops.post_project_update(
            workspace_id="1",
            message="Hi",
            recipient_emails=["missing@example.com"],
        )


def test_post_project_update_missing_file() -> None:
    ops = operations_with_transport(lambda r: httpx.Response(500))
    with pytest.raises(FileNotFoundError):
        ops.post_project_update(workspace_id="1", message="x", attachment_paths=["/no/such/file.txt"])


def test_update_post_message() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT" and request.url.path.endswith("/posts/99.json"):
            body = json.loads(request.content.decode())
            assert body == {"post": {"message": "<p>revised</p>"}}
            return httpx.Response(
                200,
                json={
                    "count": 1,
                    "results": [{"key": "posts", "id": "99"}],
                    "posts": {"99": {"id": "99", "message": "<p>revised</p>"}},
                },
            )
        raise AssertionError(request.url)

    ops = operations_with_transport(h)
    r = ops.update_post(post_id="99", message="<p>revised</p>")
    assert r["items"][0]["id"] == "99"
    assert r["items"][0]["message"] == "<p>revised</p>"


def test_update_post_story_id() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT" and request.url.path.endswith("/posts/99.json"):
            body = json.loads(request.content.decode())
            assert body == {"post": {"story_id": 42}}
            return httpx.Response(
                200,
                json={"count": 1, "results": [{"key": "posts", "id": "99"}], "posts": {"99": {"id": "99"}}},
            )
        raise AssertionError(request.url)

    ops = operations_with_transport(h)
    ops.update_post(post_id="99", story_id="42")


def test_update_post_requires_field() -> None:
    ops = operations_with_transport(lambda r: httpx.Response(500))
    with pytest.raises(ValueError, match="Provide at least one"):
        ops.update_post(post_id="99")


def test_upload_post_attachment_server_small_file(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("x")

    def h(request: httpx.Request) -> httpx.Response:
        if "/attachments.json" in request.url.path and request.method == "POST":
            return httpx.Response(
                200,
                json={"count": 1, "results": [{"key": "attachments", "id": "77"}], "attachments": {"77": {"id": "77"}}},
            )
        raise AssertionError(request.url)

    ops = operations_with_transport(h)
    aid = ops._upload_post_attachment_server(f)  # noqa: SLF001
    assert aid == "77"


def test_paginate_all_two_pages() -> None:
    n = {"p": 0}

    def h(request: httpx.Request) -> httpx.Response:
        n["p"] += 1
        if n["p"] == 1:
            return httpx.Response(
                200,
                json={
                    "count": 120,
                    "results": [{"key": "x", "id": str(i)} for i in range(100)],
                    "x": {str(i): {"id": str(i)} for i in range(100)},
                },
            )
        return httpx.Response(
            200,
            json={
                "count": 120,
                "results": [{"key": "x", "id": "101"}],
                "x": {"101": {"id": "101"}},
            },
        )

    c = KantataClient("t", api_base="https://test.invalid/api/v1", transport=httpx.MockTransport(h))
    rows = _paginate_all(c, "/x", {})
    assert len(rows) == 101
    c.close()


def test_participations_index_requires_workspace_id_helper() -> None:
    e = KantataAPIError("x", status_code=422, body="workspace_id is required")
    assert _participations_index_requires_workspace_id(e) is True
    e2 = KantataAPIError("x", status_code=400, body="workspace_id")
    assert _participations_index_requires_workspace_id(e2) is False


def test_list_my_projects_via_participations() -> None:
    """list_my_projects: users/me, participations page1, workspaces only=."""

    def h(request: httpx.Request) -> httpx.Response:
        path = str(request.url)
        if "/users/me.json" in path:
            return httpx.Response(
                200,
                json={"count": 1, "results": [{"key": "users", "id": "1"}], "users": {"1": {"id": "1"}}},
            )
        if "/participations.json" in path:
            return httpx.Response(
                200,
                json={
                    "count": 1,
                    "results": [{"key": "participations", "id": "p1"}],
                    "participations": {"p1": {"id": "p1", "workspace_id": "99", "user_id": "1"}},
                },
            )
        if "/workspaces.json" in path and "only=99" in path.replace("%2C", ","):
            return httpx.Response(
                200,
                json={
                    "count": 1,
                    "results": [{"key": "workspaces", "id": "99"}],
                    "workspaces": {"99": {"id": "99", "title": "WS"}},
                },
            )
        raise AssertionError(path)

    ops = operations_with_transport(h)
    r = ops.list_my_projects(search=None)
    assert r["items"][0]["title"] == "WS"


def test_join_project_posts_participation() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        if "/users/me.json" in str(request.url):
            return httpx.Response(
                200,
                json={"count": 1, "results": [{"key": "users", "id": "7"}], "users": {"7": {"id": "7"}}},
            )
        if request.method == "POST" and "/participations.json" in str(request.url):
            body = json.loads(request.content.decode())
            assert body["participations"][0]["workspace_id"] == 5
            return httpx.Response(
                200,
                json={"count": 0, "results": [], "participations": {}},
            )
        raise AssertionError(str(request.url))

    ops = operations_with_transport(h)
    ops.join_project(workspace_id="5", role="maven")


def test_current_user_id_raises_when_me_has_no_id() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"count": 0, "results": [], "users": {}})

    ops = operations_with_transport(h)
    with pytest.raises(RuntimeError, match="Could not resolve"):
        ops._current_user_id()  # noqa: SLF001
