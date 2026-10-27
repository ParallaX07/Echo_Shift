"""Every chamber has a hub room to walk about in, behind one door.

The hub is the only floor that is always lit and free to walk, so a take may
start on any hub tile. The room is safe to enlarge only while the start tile
stays the sole hub tile that touches the rest of the chamber: any other contact
would let a take start closer to the route than the intended solution does.
"""

from collections import deque

import pytest

from echo_shift.engine.loader import load
from echo_shift.engine.model import Position, TileType
from echo_shift.ui.layout import Layout, framed_bounds
from tests.solutions.test_solutions import LEVELS, NUMBERS

OPEN = (TileType.WALL, TileType.HUB, TileType.CONSOLE)
STEPS = ((0, -1), (1, 0), (0, 1), (-1, 0))


@pytest.fixture(params=NUMBERS, ids=lambda n: f"chamber_{n:02}")
def chamber(request):
    return load(LEVELS / f"chamber_{request.param:02}.json")


def test_the_start_is_the_hubs_only_door_and_only_console(chamber):
    assert chamber.consoles == {chamber.start}
    doors = {
        tile
        for tile in chamber.hub
        for dx, dy in STEPS
        if chamber.tile_at(Position(tile.x + dx, tile.y + dy)) not in OPEN
    }
    assert doors == {chamber.start}


def test_the_hub_is_one_connected_room(chamber):
    seen, queue = {chamber.start}, deque([chamber.start])
    while queue:
        here = queue.popleft()
        for dx, dy in STEPS:
            there = Position(here.x + dx, here.y + dy)
            if there in chamber.hub and there not in seen:
                seen.add(there)
                queue.append(there)
    assert seen == chamber.hub
    assert len(chamber.hub) >= 50  # room to walk about, not a single tile


def test_enlarged_chambers_are_bigger_than_one_screen(chamber):
    min_x, min_y, max_x, max_y = framed_bounds(chamber)
    assert max_x - min_x + 1 >= 15 and max_y - min_y + 1 >= 11
    layout = Layout.fit(1280, 720)
    assert max_y - min_y + 1 > layout.room_h // layout.min_tile  # it scrolls
