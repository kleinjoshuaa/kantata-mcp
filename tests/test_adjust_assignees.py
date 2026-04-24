"""Unit tests for adjust_story_assignees validation (no HTTP)."""

from unittest.mock import MagicMock

import pytest

from kantata_assist.operations import KantataOperations


def test_adjust_rejects_replace_combined_with_merge_flags() -> None:
    ops = KantataOperations(MagicMock())
    with pytest.raises(ValueError, match="cannot be combined"):
        ops.adjust_story_assignees(
            story_id="1",
            replace_assignee_user_ids="10,11",
            add_me=True,
        )


def test_adjust_requires_some_assignee_change() -> None:
    ops = KantataOperations(MagicMock())
    with pytest.raises(ValueError, match="Provide replace"):
        ops.adjust_story_assignees(story_id="1")


def test_list_users_requires_a_filter() -> None:
    ops = KantataOperations(MagicMock())
    with pytest.raises(ValueError, match="Provide at least one"):
        ops.list_users()
