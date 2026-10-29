"""Play the checked-in human-readable solutions through the real engine."""

import json
from pathlib import Path

import pytest

from echo_shift.engine.loader import load
from echo_shift.engine.model import Phase, initial_state
from echo_shift.engine.recording import act, enter, launch
from echo_shift.engine.turn import Accepted, InteractAtConsole, Move, Wait

LEVELS = Path(__file__).resolve().parents[2] / "levels"
MOVES = {
    "up": Move(0, -1),
    "right": Move(1, 0),
    "down": Move(0, 1),
    "left": Move(-1, 0),
    "wait": Wait(),
}


def solution_steps(number: int) -> list:
    path = LEVELS / "solutions" / f"chamber_{number:02}.json"
    return json.loads(path.read_text())["steps"]


def run_steps(state, steps, label=None):
    """Apply solution steps to `state` through the real engine; return the final state."""
    for index, command in enumerate(steps, 1):
        if isinstance(command, dict):
            result = act(state, InteractAtConsole(frozenset(command["power"])))
            assert isinstance(result, Accepted), (label, index, result)
            state = result.state
        elif command == "enter":
            updated = enter(state)
            assert updated is not state, (label, index, "enter was ignored")
            state = updated
        elif command == "launch":
            updated = launch(state)
            assert updated is not state, (label, index, "launch was ignored")
            state = updated
        else:
            result = act(state, MOVES[command])
            assert isinstance(result, Accepted), (label, index, result)
            state = result.state
            if result.succeeded:
                assert index == len(steps), (label, "solution continues after exit")
    return state


def replay(number: int):
    chamber = load(LEVELS / f"chamber_{number:02}.json")
    state = run_steps(initial_state(chamber), solution_steps(number), number)
    assert state.phase is Phase.RESULT, (number, "solution never reached the exit")
    return state


NUMBERS = sorted(
    int(path.stem[-2:])
    for path in (LEVELS / "solutions").glob("chamber_[0-9][0-9].json")
)


# Chambers built as a small hub with wings; the rest keep the large hub room.
WING_CHAMBERS = [1, 2, 3]


def test_all_six_chambers_have_a_solution():
    chambers = sorted(
        int(path.stem[-2:]) for path in LEVELS.glob("chamber_[0-9][0-9].json")
    )
    assert chambers == NUMBERS == [1, 2, 3, 4, 5, 6]


@pytest.mark.parametrize("number", NUMBERS)
def test_solution_reaches_exit(number):
    replay(number)
