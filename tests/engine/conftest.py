import pytest

from echo_shift.engine.model import (
    Chamber,
    Circuit,
    Device,
    Pad,
    Position,
    TileType,
    Zone,
)


@pytest.fixture
def chamber_factory():
    def make(*, start=None, capacity=2, console=None):
        start = start or Position(1, 1)
        console = console or Position(1, 1)
        grid = [[TileType.FLOOR for _ in range(5)] for _ in range(3)]
        for x in range(5):
            grid[0][x] = grid[2][x] = TileType.WALL
        grid[1][0] = grid[1][4] = TileType.WALL
        grid[1][1] = TileType.HUB
        grid[1][2] = TileType.PAD
        grid[1][3] = TileType.GATE
        return Chamber(
            tiles=tuple(tuple(row) for row in grid),
            start=start,
            hub=frozenset({Position(1, 1)}),
            consoles=frozenset({console}),
            capacity=capacity,
            zones=(Zone("lab", (Position(2, 1), Position(3, 1))),),
            circuits=(Circuit("lab-power", 2, ("lab",), ("gate-a",)),),
            pads=(Pad("pad-a", Position(2, 1)),),
            devices=(
                Device("gate-a", TileType.GATE, Position(3, 1), "lab-power", "pad-a"),
            ),
        )

    return make
