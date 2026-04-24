#!/usr/bin/env python3
"""Create demo Kantata workspaces, tasks, and extra participations. Loads repo root .env into the environment."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
ENV_FILE = REPO / ".env"


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = raw.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key:
            os.environ[key] = val


def main() -> int:
    load_dotenv(ENV_FILE)
    if SRC.is_dir():
        sys.path.insert(0, str(SRC))

    from kantata_assist.client import KantataAPIError, KantataClient
    from kantata_assist.config import load_access_token, load_api_base

    try:
        token = load_access_token()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        print("Ensure .env sets KANTATA_ACCESS_TOKEN or KANTATA_CREDENTIALS_PATH.", file=sys.stderr)
        return 1

    api_base = load_api_base()
    client = KantataClient(token, api_base=api_base)

    me = client.get("/users/me")
    items = KantataClient.items(me)
    me_u = items[0] if items else me
    my_id = int(me_u["id"])
    my_name = me_u.get("full_name") or me_u.get("email_address") or str(my_id)
    print(f"Authenticated as {my_name} (user id {my_id})")

    # Visible account users (exclude self for extra participations)
    others: list[dict] = []
    page = 1
    while page <= 5:
        data = client.get("/users", params={"page": page, "per_page": 100})
        batch = KantataClient.items(data)
        if not batch:
            break
        for u in batch:
            uid = int(u["id"])
            if uid != my_id:
                others.append(u)
        if len(batch) < 100:
            break
        page += 1

    extra_ids = [int(u["id"]) for u in others[:3]]
    print(f"Found {len(others)} other account users; adding up to {len(extra_ids)} to new projects.")

    stamp = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%d")
    projects_meta = [
        {
            "title": f"Assist seed — API playground ({stamp})",
            "description": "Demo project created by kantata-project/scripts/seed_demo_projects.py",
        },
        {
            "title": f"Assist seed — Integration sandbox ({stamp})",
            "description": "Second demo workspace for tasks and collaboration tests.",
        },
    ]

    created_ids: list[str] = []
    for meta in projects_meta:
        # Do not embed participations here: Kantata validates consultant-team membership
        # (members_only_mavens). Add users after create via POST /participations.
        ws_body: dict = {
            "title": meta["title"],
            "creator_role": "consultant",
            "description": meta["description"],
            "access_level": "open",
        }
        try:
            resp = client.post("/workspaces", json_body={"workspaces": [ws_body]})
        except KantataAPIError as e:
            print(f"Create workspace failed: {e}", file=sys.stderr)
            if e.body:
                print(e.body[:1500], file=sys.stderr)
            return 1
        wid = KantataClient.first_id(resp)
        if not wid:
            print(json.dumps(resp, indent=2)[:2000], file=sys.stderr)
            return 1
        created_ids.append(wid)
        print(f"Created workspace id={wid} title={meta['title']!r}")

        for uid in extra_ids:
            try:
                client.post(
                    "/participations",
                    json_body={
                        "participations": [
                            {"workspace_id": int(wid), "user_id": int(uid), "role": "maven"},
                        ]
                    },
                )
                print(f"  added participant user_id={uid} role=maven")
            except KantataAPIError as e:
                print(f"  skip participant user_id={uid}: {e}", file=sys.stderr)

        # Tasks (stories): you assigned on first, mixed on second
        stories = [
            {"title": "Kickoff — scope and API checks", "description": "Seed task 1"},
            {"title": "Wire MCP + credentials", "description": "Seed task 2"},
            {"title": "Backfill docs from Kantata responses", "description": "Seed task 3"},
        ]
        for i, st in enumerate(stories):
            assign = [my_id] if wid == created_ids[0] or i < 2 else (extra_ids[:1] or [my_id])
            row: dict = {
                "workspace_id": int(wid),
                "title": st["title"],
                "description": st["description"],
                "assignments": [{"assignee_id": int(a)} for a in assign],
            }
            try:
                sr = client.post("/stories", json_body={"stories": [row]})
                sid = KantataClient.first_id(sr)
                print(f"  story id={sid} assignees={assign} title={st['title']!r}")
            except KantataAPIError as e:
                print(f"  story create failed: {e}", file=sys.stderr)

    print(json.dumps({"workspace_ids": created_ids, "added_participant_user_ids": extra_ids}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
