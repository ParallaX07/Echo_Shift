"""Exhaust no-echo states using the canonical turn transition."""

import pytest

from echo_shift.engine.loader import load
from echo_shift.engine.model import Phase
from echo_shift.engine.search import Verdict, exhaust_without_echo
from tests.solutions.test_solutions import LEVELS, NUMBERS, replay

ECHO_CHAMBERS = [n for n in NUMBERS if n >= 3]


def test_chambers_three_to_six_are_checked():
    assert ECHO_CHAMBERS == [3, 4, 5, 6]


@pytest.mark.parametrize("number", ECHO_CHAMBERS)
def test_chamber_requires_echo(number):
    assert replay(number).phase is Phase.RESULT  # The real echo can solve it.
    chamber = load(LEVELS / f"chamber_{number:02}.json")
    proof = exhaust_without_echo(chamber)
    # A cap hit is inconclusive and fails here; only a full exhaustion proves it.
    assert proof.verdict is Verdict.UNSOLVABLE, proof
    assert proof.states > 1  # Search explored reachable states.


def test_chamber_without_an_echo_requirement_is_not_flagged():
    # Chamber 1 can be walked alone, so exhaustion finds an exit instead.
    chamber = load(LEVELS / "chamber_01.json")
    assert exhaust_without_echo(chamber).verdict is Verdict.SOLVABLE
