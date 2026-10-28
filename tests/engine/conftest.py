import pytest

from echo_shift.engine.model import (
    Cell,
    Chamber,
    Circuit,
    Conduit,
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


@pytest.fixture
def wing_chamber():
    """One corridor: hub, a lit wing with a cell and a conduit, a dark gap, a pad, a
    gate and the lift.

    x:  0 wall | 1 hub+console+start | 2 floor (wing, cell c1 worth 2)
        3 floor (wing, conduit) | 4 floor (dark) | 5 pad (pad zone) | 6 gate
        (pad zone) | 7 elevator (pad zone) | 8 wall
    Circuits: lamp (2) lights the wing and the pad zone, aux (3) does nothing,
    arc (1) makes the conduit live. Base capacity 3, so lamp+aux needs the cell.
    """
    grid = [[TileType.WALL] * 9 for _ in range(3)]
    for x, tile in enumerate(
        (
            TileType.WALL,
            TileType.CONSOLE,
            TileType.FLOOR,
            TileType.FLOOR,
            TileType.FLOOR,
            TileType.PAD,
            TileType.GATE,
            TileType.ELEVATOR,
            TileType.WALL,
        )
    ):
        grid[1][x] = tile
    hub = Position(1, 1)
    return Chamber(
        tiles=tuple(tuple(row) for row in grid),
        start=hub,
        hub=frozenset({hub}),
        consoles=frozenset({hub}),
        capacity=3,
        zones=(
            Zone("wing", (Position(2, 1), Position(3, 1))),
            Zone("pads", (Position(5, 1), Position(6, 1), Position(7, 1))),
        ),
        circuits=(
            Circuit("lamp", 2, ("wing", "pads"), ("gate-a", "lift")),
            Circuit("aux", 3),
            Circuit("arc", 1),
        ),
        pads=(Pad("pad-a", Position(5, 1), 3),),
        devices=(
            Device("gate-a", TileType.GATE, Position(6, 1), "lamp", "pad-a"),
            Device("lift", TileType.ELEVATOR, Position(7, 1), "lamp", "pad-a"),
        ),
        exit=Position(7, 1),
        cells=(Cell("c1", Position(2, 1), 2),),
        conduits=(Conduit("line", "arc", (Position(3, 1),)),),
    )
