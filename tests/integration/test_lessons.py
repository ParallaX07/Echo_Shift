"""Every guided lesson, played through the real loop with real key presses."""

import json

import pytest

from echo_shift.engine.model import Phase
from echo_shift.ui import progress

from .conftest import assert_bars_intact

pytestmark = pytest.mark.pyxel

KEYS = {
    "open_console": "E",
    "apply": "RETURN",
    "enter": "RETURN",
    "launch": "RETURN",
    "right": "RIGHT",
    "left": "LEFT",
    "up": "UP",
    "down": "DOWN",
    "wait": "SPACE",
    "retry": "R",
}


def play_step(real):
    """Press what the current lesson step asks for; the step must then be done."""
    game = real.game
    step = game.lesson.current
    if step.action == "toggle":
        target = step.target["id"]
        circuits = game.state.chamber.circuits
        while circuits[game.selection].id != target:
            real.press("DOWN")
        real.press("SPACE")
    else:
        real.press(KEYS[step.action])
    assert game.lesson.current is not step, step.id
    return step.id


@pytest.mark.parametrize("number", [1, 2, 3, 4, 5, 6])
def test_guided_lesson_runs_from_the_choice_card_to_the_cleared_chamber(real, number):
    game = real.game
    game.open_level(number)
    real.frame()
    assert game.modal == "lesson_choice"
    real.press("RETURN")
    assert game.modal is None and game.lesson is not None
    visited = []
    while game.lesson.current:
        visited.append(play_step(real))
        assert_bars_intact(real)
    assert visited == [step.id for step in game.lesson_steps]
    assert game.state.phase is Phase.RESULT and game.modal == "result"
    assert progress.load(6).unlocked == min(number + 1, 6)
    record = json.loads(
        (real.directory / "playtest.jsonl").read_text().splitlines()[-1]
    )
    assert record["completed"] and record["mode"] == "guided"


def test_the_result_card_continues_to_the_next_chamber(real):
    game = real.game
    game.open_level(1)
    real.press("RETURN")
    while game.lesson.current:
        play_step(real)
    real.press("RETURN")
    assert game.mode == "game" and game.level == 2
    assert game.modal == "lesson_choice"


def test_the_last_chamber_returns_to_level_select(real):
    game = real.game
    game.open_level(6)
    real.press("RETURN")
    while game.lesson.current:
        play_step(real)
    assert game.modal == "result" and progress.load(6).unlocked == 6
    real.press("RETURN")
    assert game.mode == "levels" and game.level == 6
