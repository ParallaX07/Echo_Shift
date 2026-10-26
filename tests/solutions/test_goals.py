"""Stored goals equal what the solver proves, and stored traces reach them."""

import json

import pytest

from echo_shift.engine.loader import load
from echo_shift.engine.search import Verdict, analyze, play
from tests.solutions.test_solutions import LEVELS, NUMBERS, solution_steps

WITH_GOALS = [n for n in NUMBERS if load(LEVELS / f"chamber_{n:02}.json").goals]


def goal_trace(number):
    path = LEVELS / "solutions" / f"chamber_{number:02}.goals.json"
    return json.loads(path.read_text())


def test_every_chamber_has_goals_and_an_idea():
    assert NUMBERS == WITH_GOALS == [1, 2, 3, 4, 5, 6]
    for number in NUMBERS:
        chamber = load(LEVELS / f"chamber_{number:02}.json")
        assert chamber.goals is not None and chamber.idea is not None


def test_chamber_ideas_follow_the_teaching_order():
    ideas = [load(LEVELS / f"chamber_{n:02}.json").idea for n in NUMBERS]
    assert ideas == [
        "movement",
        "power",
        "echo",
        "darkness",
        "timed_pads",
        "combined",
    ]


def test_difficulty_rises_with_the_chamber_number():
    turns = [load(LEVELS / f"chamber_{n:02}.json").goals.turns for n in NUMBERS]
    assert turns == sorted(set(turns)), turns  # strictly rising fewest turns


# Chamber 3's lesson records one extra wait so each step is easy to follow.
SPARE_TURNS = {3: 1}


@pytest.mark.parametrize("number", NUMBERS)
def test_the_intended_solution_is_a_shortest_one(number):
    chamber = load(LEVELS / f"chamber_{number:02}.json")
    exited, turns, _, _ = play(chamber, tuple(solution_steps(number)))
    assert exited and turns - chamber.goals.turns == SPARE_TURNS.get(number, 0)


def test_every_goal_has_a_trace_and_every_trace_has_goals():
    traces = {
        int(path.name[8:10])
        for path in (LEVELS / "solutions").glob("chamber_[0-9][0-9].goals.json")
    }
    assert traces == set(WITH_GOALS)


@pytest.mark.parametrize("number", WITH_GOALS)
def test_stored_goals_equal_the_solver_optimum(number):
    chamber = load(LEVELS / f"chamber_{number:02}.json")
    report = analyze(chamber)
    assert report.verdict is Verdict.SOLVABLE, report
    assert (chamber.goals.turns, chamber.goals.recorded) == (
        report.turns,
        report.recorded,
    )
    assert report.avoids_idea is False, "a solution skips the chamber's idea"


@pytest.mark.parametrize("number", WITH_GOALS)
def test_stored_goal_traces_achieve_the_goals(number):
    chamber = load(LEVELS / f"chamber_{number:02}.json")
    traces = goal_trace(number)
    exited, turns, _, _ = play(chamber, tuple(traces["turns"]))
    assert exited and turns == chamber.goals.turns
    exited, _, recorded, _ = play(chamber, tuple(traces["recorded"]))
    assert exited and recorded == chamber.goals.recorded
