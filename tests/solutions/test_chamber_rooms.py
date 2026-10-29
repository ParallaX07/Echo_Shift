"""Every chamber is a small hub with wings, and the map is the puzzle.

Each chamber has a small lit hub near the middle with the console and the start
inside it, a few dark wings around it and an exit well away from the hub. These
checks hold every chamber to the same design rules:

- the hub has 6 to 12 tiles, is one connected room near the middle and holds the
  start and the console;
- two or three wings leave the hub, each holding a cell, a log terminal, a pad, a
  gate or the exit, so a trip into one always brings something back;
- the exit is at least 6 steps from the hub;
- no dead space: every walkable tile is either reachable by free roam under some
  power setting (with every cell taken) or on the intended solution's path;
- the chamber measures about 14x9 to 18x11 tiles.
"""

import json
from collections import deque

import pytest

from echo_shift.engine.loader import load
from echo_shift.engine.model import Position, TileType, initial_state
from echo_shift.engine.recording import act, enter, launch
from echo_shift.engine.search import roam_graph
from echo_shift.engine.turn import InteractAtConsole
from echo_shift.ui.layout import framed_bounds
from tests.solutions.test_solutions import (
    LEVELS,
    MOVES,
    NUMBERS,
    solution_steps,
)

STEPS = ((0, -1), (1, 0), (0, 1), (-1, 0))


def ids(n):
    return f"chamber_{n:02}"


def walkable(chamber):
    return {
        Position(x, y)
        for y in range(chamber.height)
        for x in range(chamber.width)
        if chamber.tile_at(Position(x, y)) is not TileType.WALL
    }


def neighbours(tile):
    return [Position(tile.x + dx, tile.y + dy) for dx, dy in STEPS]


def terminals(number):
    data = json.loads((LEVELS / f"chamber_{number:02}.json").read_text())
    return {Position(*item["position"]) for item in data["terminals"]}


def hub_distances(chamber):
    """Walking distance from the nearest hub tile (gates count as floor)."""
    open_tiles = walkable(chamber)
    seen = {tile: 0 for tile in chamber.hub}
    queue = deque(chamber.hub)
    while queue:
        here = queue.popleft()
        for there in neighbours(here):
            if there in open_tiles and there not in seen:
                seen[there] = seen[here] + 1
                queue.append(there)
    return seen


def wings(chamber):
    """The connected groups of walkable tiles outside the hub."""
    outside = walkable(chamber) - chamber.hub
    found, left = [], set(outside)
    while left:
        group, queue = set(), deque([left.pop()])
        group.update(queue)
        while queue:
            for there in neighbours(queue.popleft()):
                if there in left:
                    left.discard(there)
                    group.add(there)
                    queue.append(there)
        found.append(group)
    return found


def solution_tiles(number, chamber):
    """Every tile the player or the echo stands on while the solution plays."""
    state, seen = initial_state(chamber), set()
    for step in solution_steps(number):
        if isinstance(step, dict):
            state = act(state, InteractAtConsole(frozenset(step["power"]))).state
        elif step in ("enter", "launch"):
            state = (enter if step == "enter" else launch)(state)
        else:
            state = act(state, MOVES[step]).state
        seen.add(state.player)
        if state.echo_position is not None:
            seen.add(state.echo_position)
    return seen


def roamable(chamber):
    """Tiles free roam can stand on under some power setting, every cell taken."""
    graph = roam_graph(chamber)
    root = graph.root(frozenset(), frozenset())
    reach = graph.reach(root, frozenset(graph.configs))
    return {tile for tile, _, _ in reach}


# ---- wing chambers -----------------------------------------------------------------


@pytest.fixture(params=NUMBERS, ids=ids)
def wing(request):
    return request.param, load(LEVELS / f"chamber_{request.param:02}.json")


def test_the_hub_is_a_small_connected_room_near_the_middle(wing):
    _, chamber = wing
    assert 6 <= len(chamber.hub) <= 12
    assert chamber.start in chamber.hub and chamber.consoles <= chamber.hub
    seen, queue = {chamber.start}, deque([chamber.start])
    while queue:
        for there in neighbours(queue.popleft()):
            if there in chamber.hub and there not in seen:
                seen.add(there)
                queue.append(there)
    assert seen == chamber.hub
    min_x, min_y, max_x, max_y = framed_bounds(chamber)
    mid_x, mid_y = (min_x + max_x) / 2, (min_y + max_y) / 2
    cx = sum(t.x for t in chamber.hub) / len(chamber.hub)
    cy = sum(t.y for t in chamber.hub) / len(chamber.hub)
    assert abs(cx - mid_x) <= (max_x - min_x) / 4
    assert abs(cy - mid_y) <= (max_y - min_y) / 4


def test_the_exit_is_far_from_the_hub(wing):
    _, chamber = wing
    assert hub_distances(chamber)[chamber.exit] >= 6


def test_two_or_three_wings_each_bring_something_back(wing):
    number, chamber = wing
    groups = wings(chamber)
    assert 2 <= len(groups) <= 3
    prizes = {cell.position for cell in chamber.cells} | terminals(number)
    prizes |= {pad.position for pad in chamber.pads}
    prizes |= {device.position for device in chamber.devices}
    for group in groups:
        assert group & prizes, f"a wing with nothing in it: {sorted(group)}"


def test_every_walkable_tile_is_used(wing):
    number, chamber = wing
    used = roamable(chamber) | solution_tiles(number, chamber)
    dead = walkable(chamber) - used
    assert not dead, f"dead space: {sorted(dead)}"


def test_cells_and_terminals_are_reachable_by_free_roam(wing):
    number, chamber = wing
    roam = roamable(chamber)
    assert {cell.position for cell in chamber.cells} <= roam
    assert terminals(number) <= roam


def test_the_chamber_fits_about_one_screen(wing):
    _, chamber = wing
    min_x, min_y, max_x, max_y = framed_bounds(chamber)
    assert 14 <= max_x - min_x + 1 <= 18
    assert 9 <= max_y - min_y + 1 <= 11


def test_the_console_and_start_are_a_short_walk_apart(wing):
    _, chamber = wing
    (console,) = chamber.consoles
    assert chamber.tile_at(console) is TileType.CONSOLE
    assert chamber.tile_at(chamber.start) is TileType.HUB
    assert 2 <= abs(console.x - chamber.start.x) + abs(console.y - chamber.start.y) <= 4
