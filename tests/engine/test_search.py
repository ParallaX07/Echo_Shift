"""The exhaustive solver on tiny chambers with known answers."""

import time
from dataclasses import replace

import pytest

from echo_shift.engine import search
from echo_shift.engine.loader import from_dict
from echo_shift.engine.model import Phase, initial_state
from echo_shift.engine.recording import act, enter, launch
from echo_shift.engine.search import (
    Constraints,
    Inconclusive,
    Limits,
    Verdict,
    analyze,
    avoids_idea,
    exhaust_without_echo,
    explore,
    play,
)
from echo_shift.engine.turn import Failed, InteractAtConsole, Move, Wait

GLYPHS = {
    "#": "wall",
    ".": "floor",
    "H": "hub",
    "P": "pad",
    "G": "gate",
    "E": "elevator",
}


def corridor(row, *, timer=0, capacity=60, max_turns=6, **extra):
    """A one-row chamber: H hub, P pad, G gate, E elevator, . floor.

    One circuit lights the whole route and powers the gate and the lift.
    """
    cells = {glyph: [] for glyph in row}
    for x, glyph in enumerate(row):
        cells[glyph].append([x, 1])
    devices = [
        {
            "id": "gate" if glyph == "G" else "lift",
            "kind": GLYPHS[glyph],
            "position": cells[glyph][0],
            "circuit": "power",
            "pad": "pad",
        }
        for glyph in "GE"
        if glyph in cells
    ]
    return from_dict(
        {
            "grid": [
                ["wall"] * len(row),
                [GLYPHS[glyph] for glyph in row],
                ["wall"] * len(row),
            ],
            "hub": cells["H"],
            "consoles": [cells["H"][0]],
            "start": cells["H"][0],
            "exit": cells["E"][0],
            "capacity": capacity,
            "max_turns": max_turns,
            "zones": [
                {
                    "id": "route",
                    "tiles": [
                        [x, 1] for x, glyph in enumerate(row) if glyph not in "#H"
                    ],
                }
            ],
            "circuits": [
                {
                    "id": "power",
                    "load": 40,
                    "zones": ["route"],
                    "devices": [device["id"] for device in devices],
                }
            ],
            "pads": [{"id": "pad", "position": cells["P"][0], "timer": timer}],
            "devices": devices,
            **extra,
        }
    )


@pytest.fixture(scope="module")
def gated():
    """The echo must hold the pad for the player to pass the gate."""
    return corridor("#HP.GE#")


@pytest.fixture(scope="module")
def gated_report(gated):
    return analyze(gated)


def test_known_optimum_and_counts(gated_report):
    report = gated_report
    assert report.verdict is Verdict.SOLVABLE
    # Record right, wait, wait (or wait, right, wait): 3 turns; walk 4 more.
    assert (report.turns, report.recorded, report.peak_load) == (7, 3, 40)
    assert report.recorded_turns == 7
    assert report.solutions == 2 and not report.solutions_capped


def test_returned_traces_replay_on_the_real_engine(gated, gated_report):
    report = gated_report
    assert play(gated, report.trace) == (True, 7, 3, 40)
    assert play(gated, report.recorded_trace) == (True, 7, 3, 40)


def test_traces_are_real_actions_not_a_private_transition(gated, gated_report):
    # Replaying through the public recording API reproduces the same exit.
    state = initial_state(gated)
    for token in gated_report.trace:
        if isinstance(token, dict):
            result = act(state, InteractAtConsole(frozenset(token["power"])))
            state = result.state
        elif token == "enter":
            state = enter(state)
        elif token == "launch":
            state = launch(state)
        else:
            result = act(state, Wait() if token == "wait" else search.MOVES[token])
            state = result.state
    assert state.phase is Phase.RESULT


def test_fewest_recorded_can_cost_more_turns_than_the_fastest_play():
    # A three-tile hub lets a take start next to the exit, so the fastest play
    # exits while recording; the fewest-recorded play walks it after a launch.
    chamber = corridor("#HHHP.E#", timer=3)
    report = analyze(chamber)
    assert report.turns == 3
    assert (report.recorded, report.recorded_turns) == (0, 5)
    assert play(chamber, report.recorded_trace)[:3] == (True, 5, 0)
    shortest = play(chamber, report.trace)
    assert shortest[:2] == (True, 3) and shortest[2] == 3  # exits mid-recording


def test_unsolvable_chamber_is_reported_as_such():
    # Holding the gate needs three recorded turns, but only one is allowed.
    chamber = corridor("#HP.GE#", max_turns=1)
    assert analyze(chamber).verdict is Verdict.UNSOLVABLE


def test_injected_shortcut_is_flagged_as_idea_skipping(gated):
    assert gated.idea is None
    assert not avoids_idea(gated, "echo")
    assert exhaust_without_echo(gated).verdict is Verdict.UNSOLVABLE
    shortcut = corridor("#HP.GE#", timer=4)  # the pad stays on long enough
    assert avoids_idea(shortcut, "echo")
    assert exhaust_without_echo(shortcut).verdict is Verdict.SOLVABLE
    flagged = analyze(replace(shortcut, idea="echo"))
    assert flagged.avoids_idea is True and flagged.recorded == 0
    assert analyze(replace(gated, idea="echo")).avoids_idea is False


def test_launch_can_be_forbidden(gated):
    assert explore(gated, Constraints(launch=False)).verdict is Verdict.UNSOLVABLE
    shortcut = corridor("#HP.GE#", timer=4)
    walked = explore(shortcut, Constraints(launch=False))
    assert walked.verdict is Verdict.SOLVABLE and walked.turns == 4
    assert play(shortcut, walked.trace)[1:3] == (4, 4)


def test_timed_pad_idea():
    solo = corridor("#HP.GE#", timer=4, max_turns=1)
    assert analyze(replace(solo, idea="echo")).avoids_idea is True  # timer carries it
    # With the timer at zero and one recorded turn, nothing opens the gate.
    assert not avoids_idea(solo, "timed_pads")
    assert avoids_idea(corridor("#HP.GE#", timer=4), "timed_pads")  # echo can hold it


def test_darkness_idea():
    def build(capacity):
        return from_dict(
            {
                "grid": [
                    ["wall"] * 6,
                    ["wall", "hub", "gate", "elevator", "wall", "wall"],
                    ["wall", "pad", "wall", "wall", "wall", "wall"],
                    ["wall"] * 6,
                ],
                "hub": [[1, 1]],
                "consoles": [[1, 1]],
                "start": [1, 1],
                "exit": [3, 1],
                "capacity": capacity,
                "max_turns": 3,
                "zones": [
                    {"id": "pad-zone", "tiles": [[1, 2]]},
                    {"id": "route", "tiles": [[2, 1], [3, 1]]},
                ],
                "circuits": [
                    {"id": "pad-lights", "load": 30, "zones": ["pad-zone"]},
                    {"id": "route-lights", "load": 30, "zones": ["route"]},
                    {"id": "machines", "load": 30, "devices": ["gate", "lift"]},
                ],
                "pads": [{"id": "pad", "position": [1, 2], "timer": 0}],
                "devices": [
                    {
                        "id": "gate",
                        "kind": "gate",
                        "position": [2, 1],
                        "circuit": "machines",
                        "pad": "pad",
                    },
                    {
                        "id": "lift",
                        "kind": "elevator",
                        "position": [3, 1],
                        "circuit": "machines",
                        "pad": "pad",
                    },
                ],
            }
        )

    # Lamps for the pad and the route fit together (60) but not with the
    # machines (90): with a budget of 70 the echo has to hold the pad in the dark.
    tight, roomy = build(70), build(90)
    assert analyze(tight).verdict is Verdict.SOLVABLE
    assert not avoids_idea(tight, "darkness")
    assert avoids_idea(roomy, "darkness")  # every lamp can stay on


def test_power_and_movement_ideas():
    # Three circuits (20 + 35 + 15) exceed the 60 budget, so powering every
    # circuit is not an option: allocation is required.
    chamber = from_dict(
        {
            "grid": [
                ["wall"] * 7,
                ["wall", "hub", "pad", "floor", "elevator", "wall", "wall"],
                ["wall"] * 7,
            ],
            "hub": [[1, 1]],
            "consoles": [[1, 1]],
            "start": [1, 1],
            "exit": [4, 1],
            "capacity": 60,
            "zones": [
                {"id": "path", "tiles": [[2, 1], [3, 1]]},
                {"id": "exit", "tiles": [[4, 1]]},
            ],
            "circuits": [
                {"id": "lights", "load": 20, "zones": ["path"]},
                {
                    "id": "lift-power",
                    "load": 35,
                    "zones": ["exit"],
                    "devices": ["lift"],
                },
                {"id": "spare", "load": 15},
            ],
            "pads": [{"id": "pad", "position": [2, 1], "timer": 3}],
            "devices": [
                {
                    "id": "lift",
                    "kind": "elevator",
                    "position": [4, 1],
                    "circuit": "lift-power",
                    "pad": "pad",
                }
            ],
        }
    )
    assert not avoids_idea(chamber, "power")
    assert not avoids_idea(chamber, "movement")  # the lift always needs power
    assert analyze(chamber).peak_load == 55
    roomy = replace(chamber, capacity=70)
    assert avoids_idea(roomy, "power")


def test_combined_idea_uses_only_what_the_chamber_exercises(gated):
    assert search.features(gated) == ("echo", "darkness")
    assert avoids_idea(gated, "combined")  # the echo can wait in the light
    shortcut = corridor("#HP.GE#", timer=4)
    assert avoids_idea(shortcut, "combined")


def test_unknown_idea_is_rejected(gated):
    with pytest.raises(ValueError, match="unknown idea"):
        avoids_idea(gated, "speed")


def test_a_tiny_state_cap_is_inconclusive_not_a_verdict(gated):
    assert explore(gated, limits=Limits(max_states=3)).verdict is Verdict.INCONCLUSIVE
    assert exhaust_without_echo(gated, max_states=2).verdict is Verdict.INCONCLUSIVE
    report = analyze(gated, max_states=3)
    assert report.verdict is Verdict.INCONCLUSIVE and report.turns is None
    with pytest.raises(Inconclusive):
        avoids_idea(gated, "darkness", Limits(max_states=3))


def test_a_passed_deadline_is_inconclusive(gated):
    late = Limits(deadline=time.monotonic() - 1)
    assert explore(gated, limits=late).verdict is Verdict.INCONCLUSIVE
    assert exhaust_without_echo(gated, max_seconds=-1).verdict is Verdict.INCONCLUSIVE


def test_the_solution_count_is_a_lower_bound_at_its_cap(gated):
    exact = explore(gated, count=True, count_cap=2)
    assert (exact.solutions, exact.capped) == (2, False)
    capped = explore(gated, count=True, count_cap=1)
    assert (capped.solutions, capped.capped) == (1, True)


def test_horizon_limits_idea_checks_to_short_plays():
    solo = corridor("#HP.GE#", timer=4, max_turns=1)
    assert avoids_idea(solo, "echo")
    assert not avoids_idea(solo, "echo", horizon=3)  # four steps are needed


def test_a_new_take_counts_turns_from_zero():
    chamber = corridor("#HP.GE#")
    state = enter(initial_state(chamber))
    failed = act(state, Move(1, 0))  # the route is dark, so this take fails
    assert isinstance(failed, Failed) and failed.state.turns == 1
    assert failed.state.phase is Phase.PREPARE
    assert enter(failed.state).turns == 0
