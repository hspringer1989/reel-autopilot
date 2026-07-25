"""Milestone picking logic + card rendering (offline, no network/DB writes)."""
from src.milestones import milestone_reached, next_goal
from src.stocks.story_cards import render_milestone_story

_MARKS = [100, 200, 500]


def test_first_milestone_reached():
    assert milestone_reached(105, set(), _MARKS) == 100


def test_announced_milestone_not_repeated():
    assert milestone_reached(105, {100}, _MARKS) is None


def test_crossing_several_marks_announces_highest():
    assert milestone_reached(230, {100}, _MARKS) == 200
    assert milestone_reached(700, set(), _MARKS) == 500


def test_below_first_mark():
    assert milestone_reached(42, set(), _MARKS) is None


def test_next_goal_and_fallback_beyond_list():
    assert next_goal(100, _MARKS) == 200
    assert next_goal(500, _MARKS) == 1000  # beyond the list: double


def test_render_milestone_card(tmp_path):
    from PIL import Image

    out = render_milestone_story(100, 200, str(tmp_path / "milestone.jpg"))
    with Image.open(out) as img:
        assert img.size == (1080, 1920)
