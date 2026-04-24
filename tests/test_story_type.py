import pytest

from kantata_assist.operations import _coerce_story_type


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("task", "task"),
        ("TASK", "task"),
        (" deliverable ", "deliverable"),
        ("Milestone", "milestone"),
        ("issue", "issue"),
    ],
)
def test_coerce_story_type_accepts_kantata_values(raw: str, expected: str) -> None:
    assert _coerce_story_type(raw) == expected


def test_coerce_story_type_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Invalid story_type"):
        _coerce_story_type("bug")
