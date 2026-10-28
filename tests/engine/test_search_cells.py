"""The solver on chambers with energy cells, free roam and live conduits.

Small chambers whose answers are worked out by hand, plus an independent oracle
that walks every state the real engine can reach (no merging, no shortcuts) and
must agree with the solver on how few turns a chamber takes.
"""

from collections import deque
from dataclasses import replace

import pytest

from echo_shift.engine import search
from echo_shift.engine.loader import from_dict
from echo_shift.engine.model import Phase, Position, initial_state
from echo_shift.engine.power import max_capacity
from echo_shift.engine.recording import act, enter, launch, retry
from echo_shift.engine.search import (
    UNCONSTRAINED,
    Constraints,
    Limits,
    Verdict,
    analyze,
    avoids_idea,
    exhaust_without_echo,
    explore,
    features,
    play,
    power_choices,
    roam_graph,
)
from echo_shift.engine.turn import Accepted, InteractAtConsole, Move, Rejected, Wait

MOVES = search.MOVES


# --- Chambers -----------------------------------------------------------------


def wing_cell(**over):
    """A lit wing next to the hub holds a cell; the lift needs what the cell adds.

    x: 1 hub (console, start) | 2 wing floor with the cell (+2) | 3 pad | 4 lift.
    The wing lamp (1) lights the wing alone and the lift circuit (4) lights the
    whole route, but the generator carries 2: only the cell makes the lift legal.
    """
    data = {
        "grid": [
            ["wall"] * 6,
            ["wall", "console", "floor", "pad", "elevator", "wall"],
            ["wall"] * 6,
        ],
        "hub": [[1, 1]],
        "consoles": [[1, 1]],
        "start": [1, 1],
        "exit": [4, 1],
        "capacity": 2,
        "max_turns": 4,
        "zones": [
            {"id": "wing", "tiles": [[2, 1]]},
            {"id": "track", "tiles": [[3, 1], [4, 1]]},
        ],
        "circuits": [
            {"id": "wing-lamp", "load": 1, "zones": ["wing"]},
            {
                "id": "lift",
                "load": 4,
                "zones": ["wing", "track"],
                "devices": ["elevator"],
            },
        ],
        "pads": [{"id": "pad", "position": [3, 1], "timer": 3}],
        "devices": [
            {
                "id": "elevator",
                "kind": "elevator",
                "position": [4, 1],
                "circuit": "lift",
                "pad": "pad",
            }
        ],
        "cells": [{"id": "c1", "position": [2, 1], "value": 2}],
    }
    data.update(over)
    return from_dict(data)


def run_cell(**over):
    """A cell lies on the route, past a gate that a timed pad holds open.

    x: 1 hub (console, start) | 2 pad (timer 5) | 3 floor | 4 gate | 5 cell (+2) |
    6 lift. The lift circuit (3) and the lamp (1) need 4: with a generator of 4 the
    lone player walks over the cell on the way, with 2 only the cell would make it
    legal, and a turn never takes one.
    """
    data = {
        "grid": [
            ["wall"] * 8,
            ["wall", "console", "pad", "floor", "gate", "floor", "elevator", "wall"],
            ["wall"] * 8,
        ],
        "hub": [[1, 1]],
        "consoles": [[1, 1]],
        "start": [1, 1],
        "exit": [6, 1],
        "capacity": 4,
        "max_turns": 2,
        "zones": [{"id": "route", "tiles": [[2, 1], [3, 1], [4, 1], [5, 1], [6, 1]]}],
        "circuits": [
            {"id": "lamp", "load": 1, "zones": ["route"], "devices": ["gate"]},
            {"id": "lift", "load": 3, "devices": ["elevator"]},
        ],
        "pads": [{"id": "pad", "position": [2, 1], "timer": 5}],
        "devices": [
            {
                "id": "gate",
                "kind": "gate",
                "position": [4, 1],
                "circuit": "lamp",
                "pad": "pad",
            },
            {
                "id": "elevator",
                "kind": "elevator",
                "position": [6, 1],
                "circuit": "lift",
                "pad": "pad",
            },
        ],
        "cells": [{"id": "c1", "position": [5, 1], "value": 2}],
    }
    data.update(over)
    return from_dict(data)


def conduit_corridor(conduit_on="arc", **over):
    """A one-lane route with a conduit tile in the middle.

    x: 1 hub (console, start) | 2 pad | 3 conduit | 4 lift. The lamp lights the
    route and powers the lift. The conduit belongs to `conduit_on`: the spare
    circuit (which can stay off) or the lamp (which the route needs).
    """
    data = {
        "grid": [
            ["wall"] * 6,
            ["wall", "console", "pad", "floor", "elevator", "wall"],
            ["wall"] * 6,
        ],
        "hub": [[1, 1]],
        "consoles": [[1, 1]],
        "start": [1, 1],
        "exit": [4, 1],
        "capacity": 2,
        "max_turns": 3,
        "zones": [{"id": "route", "tiles": [[2, 1], [3, 1], [4, 1]]}],
        "circuits": [
            {"id": "lamp", "load": 1, "zones": ["route"], "devices": ["elevator"]},
            {"id": "arc", "load": 1},
        ],
        "pads": [{"id": "pad", "position": [2, 1], "timer": 4}],
        "devices": [
            {
                "id": "elevator",
                "kind": "elevator",
                "position": [4, 1],
                "circuit": "lamp",
                "pad": "pad",
            }
        ],
        "conduits": [{"id": "line", "circuit": conduit_on, "tiles": [[3, 1]]}],
    }
    data.update(over)
    return from_dict(data)


def live_pad(with_conduit=True, **over):
    """The pad that opens the gate is a live conduit, so only the echo can stand on it.

    y=1: 1 hub (console, start) | 2-3 floor | 4 gate | 5 lift; y=2: the pad below
    x=2. The conduit shares the circuit that powers the gate and the lift.
    """
    data = {
        "grid": [
            ["wall"] * 7,
            ["wall", "console", "floor", "floor", "gate", "elevator", "wall"],
            ["wall", "wall", "pad", "wall", "wall", "wall", "wall"],
            ["wall"] * 7,
        ],
        "hub": [[1, 1]],
        "consoles": [[1, 1]],
        "start": [1, 1],
        "exit": [5, 1],
        "capacity": 3,
        "max_turns": 4,
        "zones": [
            {"id": "route", "tiles": [[2, 1], [3, 1], [4, 1], [5, 1], [2, 2]]},
        ],
        "circuits": [
            {"id": "lights", "load": 1, "zones": ["route"]},
            {"id": "machines", "load": 1, "devices": ["gate", "lift"]},
        ],
        "pads": [{"id": "pad", "position": [2, 2], "timer": 0}],
        "devices": [
            {
                "id": "gate",
                "kind": "gate",
                "position": [4, 1],
                "circuit": "machines",
                "pad": "pad",
            },
            {
                "id": "lift",
                "kind": "elevator",
                "position": [5, 1],
                "circuit": "machines",
                "pad": "pad",
            },
        ],
        "conduits": (
            [{"id": "line", "circuit": "machines", "tiles": [[2, 2]]}]
            if with_conduit
            else []
        ),
    }
    data.update(over)
    return from_dict(data)


def big_chamber(cells=True):
    """About 20 by 14: a hub of 12 tiles in the middle, a dark wing on each side.

    The west wing is a lit-on-demand room with two cells; the east wing is a lane
    with a pad, a gate and the lift. The gate and the lift need 3, the east lamp
    2, but the generator carries 3: powering both needs the cell worth 2, and the
    gate needs an echo on the pad.
    """
    width, height = 20, 14
    grid = [["wall"] * width for _ in range(height)]
    hub = [(x, y) for x in range(8, 12) for y in range(5, 8)]
    west = [(x, y) for x in range(1, 8) for y in range(4, 9)]
    east = [(x, 6) for x in range(12, 19)]
    for x, y in hub:
        grid[y][x] = "hub"
    for x, y in west + east:
        grid[y][x] = "floor"
    grid[6][9] = "console"
    grid[6][14], grid[6][16], grid[6][18] = "pad", "gate", "elevator"
    return from_dict(
        {
            "grid": grid,
            "hub": [list(tile) for tile in hub],
            "consoles": [[9, 6]],
            "start": [11, 6],
            "exit": [18, 6],
            "capacity": 3,
            "max_turns": 12,
            "zones": [
                {"id": "west", "tiles": [list(tile) for tile in west]},
                {"id": "east", "tiles": [list(tile) for tile in east]},
            ],
            "circuits": [
                {"id": "west-lamp", "load": 2, "zones": ["west"]},
                {"id": "east-lamp", "load": 2, "zones": ["east"]},
                {"id": "machines", "load": 3, "devices": ["gate", "lift"]},
            ],
            "pads": [{"id": "pad", "position": [14, 6], "timer": 0}],
            "devices": [
                {
                    "id": "gate",
                    "kind": "gate",
                    "position": [16, 6],
                    "circuit": "machines",
                    "pad": "pad",
                },
                {
                    "id": "lift",
                    "kind": "elevator",
                    "position": [18, 6],
                    "circuit": "machines",
                    "pad": "pad",
                },
            ],
            "cells": (
                [
                    {"id": "c1", "position": [2, 5], "value": 2},
                    {"id": "c2", "position": [2, 7], "value": 1},
                ]
                if cells
                else []
            ),
        }
    )


# --- Helpers --------------------------------------------------------------------


def walk(chamber, trace):
    """Yield (token, state after it) while playing a trace on the real engine."""
    state = initial_state(chamber)
    for token in trace:
        if isinstance(token, dict):
            state = act(state, InteractAtConsole(frozenset(token["power"]))).state
        elif token == "enter":
            state = enter(state)
        elif token == "launch":
            state = launch(state)
        else:
            state = act(state, Wait() if token == "wait" else MOVES[token]).state
        yield token, state


def brute_force(chamber, cap, max_states=2_000_000):
    """Fewest turns of any play, found by walking every state the engine reaches.

    Free roam, takes (failed ones too), launches, console changes and restarts are
    all tried one engine call at a time. Plays whose turn count passes `cap` are
    dropped, so the answer is only as exact as `cap` is high: pass the solver's
    answer minus one and it must still find that answer.
    """
    configs = power_choices(chamber, max_capacity(chamber))
    actions = [*MOVES.values(), Wait(), *(InteractAtConsole(c) for c in configs)]
    start = initial_state(chamber)
    seen = {(start.search_key(), 0)}
    queue = deque([start])
    best = None
    while queue:
        state = queue.popleft()
        children = []
        for action in actions:
            result = act(state, action)
            if isinstance(result, Rejected):
                continue
            if isinstance(result, Accepted) and result.succeeded:
                turns = result.state.turns
                best = turns if best is None else min(best, turns)
                continue
            children.append(result.state)
        if state.phase in (Phase.PREPARE, Phase.RECORDING):
            children.append(enter(state))
        if state.phase is Phase.COMMITTED:
            children.append(launch(state))
        if state.phase is Phase.REPLAY:
            children.append(retry(state))
        for child in children:
            if child.phase is Phase.PREPARE:
                child = replace(child, turns=0)  # the next take counts from zero
            if child is state or child.turns > cap:
                continue
            key = (child.search_key(), child.turns)
            if key not in seen:
                seen.add(key)
                queue.append(child)
                assert len(seen) < max_states, "oracle too large"
    return best


# --- Free roam, cells and capacity ------------------------------------------------


def test_free_roam_takes_a_cell_in_a_lit_wing_before_the_lift_is_affordable():
    chamber = wing_cell()
    report = analyze(chamber)
    assert report.verdict is Verdict.SOLVABLE
    assert (report.turns, report.recorded) == (3, 0)
    # Three turns of replay; everything before it is free walking and switching.
    assert report.peak_load == 4 > chamber.capacity
    states = list(walk(chamber, report.trace))
    tokens = [token for token, _ in states]
    launched = tokens.index("launch")
    assert "right" in tokens[:launched]  # into the wing, before any turn
    assert {"power": ["lift"]} in tokens[:launched]
    assert states[launched][1].cells_taken == {"c1"}
    # Without the cell the lift can never be powered.
    assert analyze(replace(chamber, cells=())).verdict is Verdict.UNSOLVABLE
    assert play(chamber, report.trace)[:2] == (True, 3)


def test_the_wing_walk_is_a_zero_cost_closure_over_tile_power_and_cells():
    chamber = wing_cell()
    graph = roam_graph(chamber)
    start = graph.root(frozenset(), frozenset())
    reached = graph.reach(start, frozenset(graph.configs))
    wing, hub = Position(2, 1), Position(1, 1)
    # The wing is dark until its lamp is on; then the cell is within reach.
    assert not any(tile == wing and not config for tile, config, _ in reached)
    assert (wing, frozenset({"wing-lamp"}), frozenset({"c1"})) in reached
    # The lift setting only exists once the cell has been taken.
    lift = [node for node in reached if node[1] == {"lift"}]
    assert lift and all(cells == {"c1"} for _, _, cells in lift)
    assert (hub, frozenset({"lift"}), frozenset({"c1"})) in reached
    # Every node is what the engine itself reaches by that walk.
    for node, path in reached.items():
        state = initial_state(chamber)
        for token in path:
            if isinstance(token, dict):
                state = act(state, InteractAtConsole(frozenset(token["power"]))).state
            else:
                state = act(state, MOVES[token]).state
        assert state.search_key() == graph.state(node).search_key()


def test_a_constraint_filters_the_free_power_changes_it_does_not_rebuild_the_graph():
    chamber = wing_cell()
    assert roam_graph(chamber) is roam_graph(chamber)
    # With nothing ever powered the wing stays dark and the cell out of reach.
    stuck = explore(chamber, Constraints(config_ok=lambda config: not config))
    assert stuck.verdict is Verdict.UNSOLVABLE


ORACLE_CHAMBERS = {
    "wing cell": (wing_cell, 2),
    "a cell on the route is not taken": (run_cell, 4),
    "conduit on a spare circuit": (conduit_corridor, 2),
}


@pytest.mark.parametrize("name", ORACLE_CHAMBERS)
def test_the_solver_agrees_with_walking_every_state(name):
    build, cap = ORACLE_CHAMBERS[name]
    chamber = build()
    found = explore(chamber)
    assert found.verdict is Verdict.SOLVABLE
    assert brute_force(chamber, cap) == found.turns == cap + 1


def test_the_oracle_finds_nothing_where_the_solver_finds_nothing():
    chamber = conduit_corridor("lamp")
    assert explore(chamber).verdict is Verdict.UNSOLVABLE
    assert brute_force(chamber, 6) is None


# --- Conduits -----------------------------------------------------------------


def test_a_powered_conduit_blocks_the_route_it_lies_on():
    clear = conduit_corridor("arc", conduits=[])
    assert explore(clear).turns == 3
    # The conduit on a circuit that can stay off costs nothing.
    spare = conduit_corridor("arc")
    found = explore(spare)
    assert found.turns == 3
    assert not any(
        isinstance(token, dict) and "arc" in token["power"] for token in found.trace
    )
    # The conduit on the lamp: the route is dark without it, deadly with it.
    assert explore(conduit_corridor("lamp")).verdict is Verdict.UNSOLVABLE
    # Powering the spare circuit would block the route, so that play never wins.
    only_arc = Constraints(config_ok=lambda config: "arc" in config or not config)
    assert explore(spare, only_arc).verdict is Verdict.UNSOLVABLE


def test_free_roam_will_not_step_on_a_live_conduit():
    chamber = conduit_corridor("lamp", conduits=[])
    live = replace(chamber, conduits=conduit_corridor("lamp").conduits)
    graph = roam_graph(live)
    reached = graph.reach(
        graph.root(frozenset(), frozenset()), frozenset(graph.configs)
    )
    assert not any(
        tile == Position(3, 1) and "lamp" in config for tile, config, _ in reached
    )


def test_the_echo_is_immune_to_a_live_conduit_and_the_darkness_idea_notices():
    chamber = live_pad()
    found = explore(chamber)
    assert found.verdict is Verdict.SOLVABLE
    # The echo has to stand on the pad while its conduit is live.
    assert not avoids_idea(chamber, "darkness")
    assert avoids_idea(live_pad(with_conduit=False), "darkness")


def test_features_count_cells_as_power_and_conduits_as_darkness():
    spare = conduit_corridor("arc")
    plain = replace(spare, conduits=())
    assert "darkness" in features(plain)  # a circuit lights a zone
    unlit = replace(
        spare,
        zones=(),
        circuits=tuple(replace(c, zones=()) for c in spare.circuits),
    )
    assert "darkness" in features(unlit)
    assert "darkness" not in features(replace(unlit, conduits=()))
    # Plenty of generator, but cells are a power mechanic all the same.
    roomy = replace(wing_cell(), capacity=60)
    assert "power" in features(roomy)
    assert "power" not in features(replace(roomy, cells=()))


# --- The no-echo proof --------------------------------------------------------


def test_a_play_with_no_echo_grows_the_generator_with_cells_as_it_goes():
    chamber = wing_cell()
    assert exhaust_without_echo(chamber).verdict is Verdict.SOLVABLE
    # Cell by cell: once the wing cell is gone the same walk wins nothing.
    assert exhaust_without_echo(replace(chamber, cells=())).verdict is (
        Verdict.UNSOLVABLE
    )


def test_the_no_echo_proof_is_exhaustive_when_the_cell_cannot_be_fetched():
    # The lift needs the cell, but the cell is on the far side of a gate and a
    # turn never takes it: nothing, with or without an echo, powers the lift.
    chamber = run_cell(capacity=2)
    assert exhaust_without_echo(chamber).verdict is Verdict.UNSOLVABLE
    assert explore(chamber).verdict is Verdict.UNSOLVABLE
    # With room for the lift and the lamp no echo is needed.
    roomy = run_cell()
    assert exhaust_without_echo(roomy).verdict is Verdict.SOLVABLE
    assert search._exhaust(roomy, Limits(), horizon=5).verdict is Verdict.SOLVABLE
    assert search._exhaust(roomy, Limits(), horizon=4).verdict is Verdict.UNSOLVABLE


def test_a_cell_that_only_a_run_can_reach_is_never_taken_by_the_optimum():
    chamber = run_cell()
    found = explore(chamber, count=True)
    assert found.verdict is Verdict.SOLVABLE and found.turns == 5
    states = list(walk(chamber, found.trace))
    # The route crosses the cell's tile, but only free roam would take it.
    assert any(state.player == Position(5, 1) for _, state in states)
    assert all(state.cells_taken == frozenset() for _, state in states)
    assert play(chamber, found.trace)[:2] == (True, 5)
    assert analyze(chamber).peak_load == 4  # lamp and lift on the base generator


# --- A large chamber ----------------------------------------------------------------


def test_a_large_chamber_with_a_wide_hub_and_two_wings_stays_fast():
    chamber = big_chamber()
    assert (chamber.width, chamber.height, len(chamber.hub)) == (20, 14, 12)
    found = explore(chamber, limits=Limits(max_states=80_000))
    assert found.verdict is Verdict.SOLVABLE
    assert found.turns == 13
    states = list(walk(chamber, found.trace))
    launched = [token for token, _ in states].index("launch")
    # The big cell is fetched in the free walk before the launch.
    assert "c1" in states[launched][1].cells_taken
    assert play(chamber, found.trace)[:2] == (True, 13)
    assert exhaust_without_echo(chamber, max_states=80_000).verdict is (
        Verdict.UNSOLVABLE
    )
    # With no cell the generator never carries both, within a play as long as this.
    short = Constraints(max_turns=13)
    assert explore(replace(chamber, cells=()), short).verdict is Verdict.UNSOLVABLE


# --- State identity ---------------------------------------------------------------------


def key_of(chamber, constraints=UNCONSTRAINED):
    return search._Search(chamber, constraints, Limits(), 1)._key


def saved_take(chamber, commands, start=None):
    state = enter(initial_state(chamber))
    state = replace(state, echo_start=start or chamber.start)
    state = replace(state, recording=tuple(commands))
    return replace(state, phase=Phase.COMMITTED)


def test_takes_that_stand_on_the_same_pads_at_the_same_times_share_a_key():
    chamber = big_chamber()
    keys = key_of(chamber)
    up, down, right, wait = Move(0, -1), Move(0, 1), Move(1, 0), Wait()
    # Two walks to the pad at turn five that differ only where nothing is there.
    a = saved_take(chamber, [up, down, right, right, right])
    b = saved_take(chamber, [wait, wait, right, right, right])
    assert a.recording != b.recording
    assert keys(a) == keys(b)
    # Standing on it on other turns is another take.
    c = saved_take(chamber, [right, right, right, wait, wait])
    assert keys(a) != keys(c)
    # Over a gate tile the commands stay in the key: the echo may be held back.
    over_a = saved_take(chamber, [up, down, *[right] * 5])
    over_b = saved_take(chamber, [wait, wait, *[right] * 5])
    assert keys(over_a) != keys(over_b)


def test_a_constraint_that_reads_the_state_keeps_the_commands_in_the_key():
    chamber = big_chamber()
    up, down, right, wait = Move(0, -1), Move(0, 1), Move(1, 0), Wait()
    a = saved_take(chamber, [up, down, right, right, right])
    b = saved_take(chamber, [wait, wait, right, right, right])
    opaque = key_of(chamber, Constraints(state_ok=lambda state: True))
    assert opaque(a) != opaque(b)
    # A constraint on the echo's safety tells tiles apart by what lights them.
    granular = key_of(chamber, Constraints(echo_safe=True))
    lit_by_west = saved_take(chamber, [Move(-1, 0)] * 4)
    hub_only = saved_take(chamber, [wait] * 4)
    assert granular(lit_by_west) != granular(hub_only)
    assert key_of(chamber)(lit_by_west) == key_of(chamber)(hub_only)


def test_an_echo_that_will_not_touch_a_pad_again_is_no_echo_at_all():
    chamber = big_chamber()
    keys = key_of(chamber)
    launched = launch(saved_take(chamber, [Move(0, -1), Wait()]))
    assert launched.echo_position is not None
    gone = replace(
        launched, recording=(), echo_position=None, echo_index=0, echo_hold=0
    )
    assert keys(launched) == keys(gone)
