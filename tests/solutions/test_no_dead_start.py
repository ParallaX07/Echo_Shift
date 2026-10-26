"""No chamber can be left in a state from which its recorded solution is lost.

A chamber has a dead start if some legal play before the solution makes it
impossible to finish. Every prefix below is a play a player can make, and each
must leave the recorded solution playable from the state it reaches:

- every power setting the console accepts before a take;
- walking around the hub (leaving it is refused and changes nothing);
- starting a take and failing it (walking into the dark with the power off);
- starting a take, recording part of the solution's walk and clearing (C);
- saving that partial take and clearing (C);
- retrying from launch (R) after any number of the solution's replay steps.

Clearing and retrying are the exits from a bad take or run, so the check also
shows that each of them really returns to a solvable start.
"""

import pytest

from echo_shift.engine.loader import load
from echo_shift.engine.model import Phase, initial_state
from echo_shift.engine.recording import act, clear, enter, launch, retry
from echo_shift.engine.search import power_choices
from echo_shift.engine.turn import Accepted, Failed, InteractAtConsole, Move, Rejected
from tests.solutions.test_solutions import (
    LEVELS,
    MOVES,
    NUMBERS,
    run_steps,
    solution_steps,
)

DIRECTIONS = [MOVES[name] for name in ("up", "right", "down", "left")]


def finishes(state, steps, label):
    assert run_steps(state, steps, label).phase is Phase.RESULT, label


def split(steps):
    """The take (up to its save) and the replay (from launch) of a solution."""
    save = [i for i, step in enumerate(steps) if step == "enter"][1]
    return steps[: save + 1], steps[save + 1 :]


@pytest.fixture(params=NUMBERS, ids=lambda n: f"chamber_{n:02}")
def case(request):
    number = request.param
    chamber = load(LEVELS / f"chamber_{number:02}.json")
    return number, chamber, initial_state(chamber), solution_steps(number)


def test_every_legal_power_setting_before_a_take(case):
    number, chamber, start, steps = case
    configs = power_choices(chamber)
    assert frozenset() in configs
    for config in configs:
        result = act(start, InteractAtConsole(config))
        assert isinstance(result, Accepted), (number, config, result)
        finishes(result.state, steps, (number, "power", sorted(config)))


def test_walking_in_the_hub_never_loses_the_start(case):
    number, chamber, start, steps = case
    for direction in DIRECTIONS:
        result = act(start, direction)
        if isinstance(result, Rejected):
            assert result.state == start  # leaving the hub is refused outright
            continue
        assert isinstance(result, Accepted)
        assert result.state.player in chamber.hub
        back = act(result.state, Move(-direction.dx, -direction.dy))
        assert isinstance(back, Accepted) and back.state.player == chamber.start
        finishes(back.state, steps, (number, "hub walk", direction))


def test_a_failed_take_returns_to_a_solvable_start(case):
    number, _, start, steps = case
    failed = 0
    for direction in DIRECTIONS:
        result = act(enter(start), direction)
        if isinstance(result, Failed):  # a step into the dark with nothing powered
            failed += 1
            assert result.state.phase is Phase.PREPARE and not result.state.recording
            finishes(result.state, steps, (number, "failed take", direction))
    assert failed, "no unlit step to fail on"


def test_clearing_a_partial_take_returns_to_a_solvable_start(case):
    number, _, start, steps = case
    take, _ = split(steps)
    walk = take[take.index("enter") + 1 : -1]  # the recorded moves and waits
    prepared = run_steps(start, take[: take.index("enter")], number)  # power only
    for kept in range(len(walk) + 1):
        recording = run_steps(enter(prepared), walk[:kept], (number, kept))
        assert recording.phase is Phase.RECORDING
        finishes(clear(recording), steps, (number, "abandoned take", kept))
        saved = enter(recording)
        assert saved.phase is Phase.COMMITTED
        finishes(clear(saved), steps, (number, "saved then cleared", kept))


def test_retrying_from_launch_keeps_the_solution_playable(case):
    number, chamber, start, steps = case
    take, replay = split(steps)
    launched = run_steps(start, [*take, *replay[: replay.index("launch") + 1]], number)
    assert launched.phase is Phase.REPLAY
    moves = replay[replay.index("launch") + 1 :]
    for done in range(len(moves)):  # R after `done` steps, before the exit
        midway = run_steps(launched, moves[:done], (number, done))
        assert midway.phase is Phase.REPLAY
        restored = retry(midway)
        assert restored.turns == launched.turns and restored.player == chamber.start
        finishes(restored, moves, (number, "retry", done))
    assert launch(launched) is launched  # a launched echo cannot be launched twice
