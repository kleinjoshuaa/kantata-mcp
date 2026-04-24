#!/usr/bin/env python3
"""Create Kantata workspaces you are not on, but can join (open + remove your participation after a backup member)."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
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


def _paginate_participations(client, **params: str | int) -> list[dict]:
    from kantata_assist.client import KantataClient

    out: list[dict] = []
    page = 1
    while page <= 20:
        p = {**{k: str(v) for k, v in params.items()}, "page": page, "per_page": 100}
        data = client.get("/participations", params=p)
        batch = KantataClient.items(data)
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return out


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
        return 1

    client = KantataClient(token, api_base=load_api_base())

    me = client.get("/users/me")
    items = KantataClient.items(me)
    me_u = items[0] if items else me
    my_id = int(me_u["id"])

    # Backup member so workspace still has a consultant after you leave
    others: list[int] = []
    page = 1
    while page <= 5:
        data = client.get("/users", params={"page": page, "per_page": 100})
        batch = KantataClient.items(data)
        for u in batch:
            uid = int(u["id"])
            if uid != my_id:
                others.append(uid)
        if len(batch) < 100:
            break
        page += 1

    if not others:
        print("No other account user to hold the project after you leave; aborting.", file=sys.stderr)
        return 1

    backup_id = others[0]
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    titles = [
        f"Joinable seed — Orbit ({stamp})",
        f"Joinable seed — Nebula ({stamp})",
        f"Joinable seed — Quasar ({stamp})",
    ]

    created: list[str] = []
    for title in titles:
        try:
            resp = client.post(
                "/workspaces",
                json_body={
                    "workspaces": [
                        {
                            "title": title,
                            "creator_role": "consultant",
                            "description": "Open project; creator participation removed so you can join via kantata join-project.",
                            "access_level": "open",
                        }
                    ]
                },
            )
        except KantataAPIError as e:
            print(f"Create failed: {e}", file=sys.stderr)
            return 1
        wid = KantataClient.first_id(resp)
        if not wid:
            print(json.dumps(resp, indent=2)[:2000], file=sys.stderr)
            return 1
        print(f"Created workspace id={wid} title={title!r}")

        try:
            client.post(
                "/participations",
                json_body={
                    "participations": [
                        {"workspace_id": int(wid), "user_id": backup_id, "role": "maven"},
                    ]
                },
            )
            print(f"  ensured backup participant user_id={backup_id}")
        except KantataAPIError as e:
            print(f"  backup participant failed: {e}", file=sys.stderr)

        # Creator is team lead; Kantata rejects DELETE self until another user is team lead.
        by_user: dict[int, dict] = {}
        for p in _paginate_participations(client, workspace_id=int(wid)):
            uid = int(p.get("user_id") or 0)
            if uid:
                by_user[uid] = p
        my_p = by_user.get(my_id)
        bk_p = by_user.get(backup_id)
        if not my_p or not bk_p:
            print(f"  missing participation (me={my_p is not None} backup={bk_p is not None})", file=sys.stderr)
            created.append(wid)
            continue
        my_pid, bk_pid = my_p.get("id"), bk_p.get("id")
        if my_pid is None or bk_pid is None:
            print(f"  participation ids missing me={my_pid!r} backup={bk_pid!r}", file=sys.stderr)
            created.append(wid)
            continue
        try:
            client.put(
                f"/participations/{bk_pid}",
                json_body={"participation": {"team_lead": True}},
            )
            client.put(
                f"/participations/{my_pid}",
                json_body={"participation": {"team_lead": False}},
            )
            client.delete(f"/participations/{my_pid}")
            print(f"  transferred lead to user {backup_id}, removed your participation id={my_pid}")
        except KantataAPIError as e:
            print(f"  leave project failed: {e}", file=sys.stderr)

        created.append(wid)

    print(json.dumps({"workspace_ids": created, "backup_user_id": backup_id}, indent=2))
    print("Join with: kantata join-project <workspace_id>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
