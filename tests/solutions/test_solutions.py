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


def replay(number: int):
    chamber = load(LEVELS / f"chamber_{number:02}.json")
    steps = json.loads(
        (LEVELS / "solutions" / f"chamber_{number:02}.json").read_text()
    )["steps"]
    state = initial_state(chamber)
    succeeded = False
    for index, command in enumerate(steps, 1):
        if isinstance(command, dict):
            result = act(state, InteractAtConsole(frozenset(command["power"])))
            assert isinstance(result, Accepted), (number, index, result)
            state = result.state
        elif command == "enter":
            updated = enter(state)
            assert updated is not state, (number, index, "enter was ignored")
            state = updated
        elif command == "launch":
            updated = launch(state)
            assert updated is not state, (number, index, "launch was ignored")
            state = updated
        else:
            result = act(state, MOVES[command])
            assert isinstance(result, Accepted), (number, index, result)
            state = result.state
            succeeded = result.succeeded
            if succeeded:
                assert index == len(steps), (number, "solution continues after exit")
    assert succeeded, (number, "solution never reached the exit")
    assert state.phase is Phase.RESULT
    return state


@pytest.mark.parametrize(
    "number",
    sorted(
        int(path.stem[-2:])
        for path in (LEVELS / "solutions").glob("chamber_[0-9][0-9].json")
    ),
)
def test_solution_reaches_exit(number):
    replay(number)
