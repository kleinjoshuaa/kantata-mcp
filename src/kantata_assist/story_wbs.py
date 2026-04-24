"""Schedule-style WBS codes derived from Kantata story tree + position (UI-aligned)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _position_sort_key(item: Mapping[str, Any]) -> tuple[int, str]:
    pos = item.get("position")
    try:
        ip = int(pos) if pos is not None else 0
    except (TypeError, ValueError):
        ip = 0
    sid = item.get("id")
    return (ip, str(sid) if sid is not None else "")


def _parent_id(item: Mapping[str, Any]) -> str | None:
    p = item.get("parent_id")
    if p is None or p == "":
        return None
    return str(p)


def attach_schedule_wbs(items: list[dict[str, Any]]) -> None:
    """Set each story's ``wbs`` to a schedule-style code (e.g. ``4.3.1``).

    Kantata's API does not return outline numbers; the product builds them from
    parent/child links and ``position`` (ascending = earlier in the schedule).

    * Roots are stories with no ``parent_id`` or whose parent is not in this
      ``items`` list (e.g. filtered API response).
    * Siblings are ordered by ``position`` ascending, then ``id``.

    When ``items`` is the full task list for a workspace, codes match the WBS
    column in the Kantata schedule for that workspace. Partial lists can
    diverge or mark unreachable rows with ``wbs: null``.
    """
    if not items:
        return

    ids = {str(x["id"]) for x in items if x.get("id") is not None}
    roots = [x for x in items if _parent_id(x) is None or _parent_id(x) not in ids]
    roots_sorted = sorted(roots, key=_position_sort_key)

    children: dict[str, list[dict[str, Any]]] = {}
    for x in items:
        pk = _parent_id(x)
        if pk is None:
            continue
        children.setdefault(pk, []).append(x)
    for lst in children.values():
        lst.sort(key=_position_sort_key)

    assigned: set[str] = set()

    def visit(node: dict[str, Any], code: str) -> None:
        nid = node.get("id")
        if nid is None:
            return
        sid = str(nid)
        node["wbs"] = code
        assigned.add(sid)
        for i, child in enumerate(children.get(sid, []), start=1):
            visit(child, f"{code}.{i}")

    for i, root in enumerate(roots_sorted, start=1):
        visit(root, str(i))

    for x in items:
        if x.get("id") is None:
            continue
        if str(x["id"]) not in assigned:
            x["wbs"] = None
