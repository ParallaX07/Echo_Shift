"""Exhaust no-echo states using the canonical turn transition."""

from collections import deque
from dataclasses import replace
from itertools import combinations

import pytest

from echo_shift.engine.loader import load
from echo_shift.engine.model import Phase, initial_state
from echo_shift.engine.power import apply
from echo_shift.engine.turn import (
    Accepted,
    Failed,
    InteractAtConsole,
    Move,
    Wait,
    step,
)
from tests.solutions.test_solutions import LEVELS, replay


def power_choices(chamber):
    ids = [circuit.id for circuit in chamber.circuits]
    return tuple(
        choice
        for size in range(len(ids) + 1)
        for names in combinations(ids, size)
        if apply(chamber, choice := frozenset(names)).ok
    )


def exhaust_without_echo(chamber):
    choices = power_choices(chamber)
    queue = deque(
        replace(initial_state(chamber, choice), phase=Phase.REPLAY)
        for choice in choices
    )
    seen = {state.search_key() for state in queue}
    actions = (
        Move(0, -1),
        Move(1, 0),
        Move(0, 1),
        Move(-1, 0),
        Wait(),
        *(InteractAtConsole(choice) for choice in choices),
    )
    while queue:
        state = queue.popleft()
        for action in actions:
            result = step(state, action)
            if isinstance(result, Failed):
                continue
            if not isinstance(result, Accepted):
                continue
            assert not result.succeeded, "exit reachable without an echo"
            key = result.state.search_key()
            if key not in seen:
                seen.add(key)
                queue.append(result.state)
    return len(seen)


@pytest.mark.parametrize(
    "number",
    sorted(
        int(path.stem[-2:])
        for path in LEVELS.glob("chamber_[0-9][0-9].json")
        if int(path.stem[-2:]) >= 3
    ),
)
def test_chamber_requires_echo(number):
    assert replay(number).phase is Phase.RESULT  # The real echo can solve it.
    chamber = load(LEVELS / f"chamber_{number:02}.json")
    assert exhaust_without_echo(chamber) > 1  # Search explored reachable states.
