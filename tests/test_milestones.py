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


def test_milestone_number_never_leaves_the_canvas(tmp_path):
    """The design fixes the big number at 300 px, which only holds up to ~5
    digits — "100.000" would bleed off both edges. Every configured milestone
    must stay inside the 68 px content column."""
    from PIL import Image

    import config

    for mark in config.FOLLOWER_MILESTONES:
        out = render_milestone_story(mark, next_goal(mark), str(tmp_path / f"{mark}.jpg"))
        with Image.open(out) as img:
            px = img.convert("RGB").load()
            xs = [x for x in range(1080) for y in range(361, 574, 4)
                  if min(px[x, y]) > 215]
        assert xs, f"{mark}: keine Zahl gerendert"
        assert 60 <= min(xs) and max(xs) <= 1020, \
            f"{mark}: Zahl läuft aus dem Bild ({min(xs)}…{max(xs)})"
