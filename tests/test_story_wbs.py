"""Tests for client-side schedule WBS numbering."""

from __future__ import annotations

from kantata_assist.story_wbs import attach_schedule_wbs


def test_attach_schedule_wbs_nested_tree_matches_kantata_order() -> None:
    """Order mirrors integration sandbox: roots by ascending position; children same."""
    items = [
        {"id": "g", "title": "Gamma", "parent_id": None, "position": 99930000},
        {"id": "b", "title": "Beta", "parent_id": None, "position": 99940000},
        {"id": "a", "title": "Alpha", "parent_id": None, "position": 99950000},
        {"id": "n", "title": "Nested", "parent_id": None, "position": 99970000},
        {"id": "bf", "title": "Backfill", "parent_id": None, "position": 99980000},
        {"id": "w", "title": "Wire", "parent_id": None, "position": 99990000},
        {"id": "k", "title": "Kickoff", "parent_id": None, "position": 100000000},
        {"id": "t3", "title": "track 3", "parent_id": "n", "position": 99980000},
        {"id": "t2", "title": "track 2", "parent_id": "n", "position": 99990000},
        {"id": "t1", "title": "track 1", "parent_id": "n", "position": 100000000},
        {"id": "leaf3", "title": "leaf 3", "parent_id": "t3", "position": 100000000},
        {"id": "leaf2", "title": "leaf 2", "parent_id": "t2", "position": 100000000},
        {"id": "leaf1", "title": "leaf 1", "parent_id": "t1", "position": 100000000},
    ]
    attach_schedule_wbs(items)
    by_id = {x["id"]: x["wbs"] for x in items}
    assert by_id["g"] == "1"
    assert by_id["b"] == "2"
    assert by_id["a"] == "3"
    assert by_id["n"] == "4"
    assert by_id["t3"] == "4.1"
    assert by_id["t2"] == "4.2"
    assert by_id["t1"] == "4.3"
    assert by_id["leaf3"] == "4.1.1"
    assert by_id["leaf2"] == "4.2.1"
    assert by_id["leaf1"] == "4.3.1"
    assert by_id["bf"] == "5"
    assert by_id["w"] == "6"
    assert by_id["k"] == "7"


def test_attach_schedule_wbs_orphan_parent_treated_as_root() -> None:
    items = [
        {"id": "1", "parent_id": "missing", "position": 1},
        {"id": "2", "parent_id": "1", "position": 1},
    ]
    attach_schedule_wbs(items)
    assert items[0]["wbs"] == "1"
    assert items[1]["wbs"] == "1.1"


def test_attach_schedule_wbs_cycle_or_unreachable_gets_null() -> None:
    """If nothing is reachable from computed roots, leave wbs null (defensive)."""
    items = [
        {"id": "1", "parent_id": "2", "position": 1},
        {"id": "2", "parent_id": "1", "position": 1},
    ]
    attach_schedule_wbs(items)
    assert items[0]["wbs"] is None
    assert items[1]["wbs"] is None
