from echo_shift.engine.loader import load
from echo_shift.engine.model import Position
from echo_shift.paths import resource_path
from echo_shift.ui import cues


def chamber(rows: list[str]):
    """'#' wall, 'h' hub, 's' hub start, '.' floor outside the hub."""
    hub = {
        Position(x, y)
        for y, row in enumerate(rows)
        for x, c in enumerate(row)
        if c in "hs"
    }
    start = next(
        Position(x, y)
        for y, row in enumerate(rows)
        for x, c in enumerate(row)
        if c == "s"
    )
    tiles = [["wall" if c == "#" else "floor" for c in row] for row in rows]
    return load_chamber(tiles, hub, start)


def load_chamber(tiles, hub, start):
    from echo_shift.engine.model import Chamber

    return Chamber(tiles=tiles, start=start, hub=hub, consoles={start}, capacity=0)


def test_a_hub_tile_touching_outside_floor_is_a_threshold():
    room = chamber(["#####", "#shh.", "#hhh#", "#####"])
    assert cues.hub_thresholds(room) == {Position(1, 1), Position(3, 1)}


def test_pillars_and_walls_do_not_make_thresholds():
    room = chamber(["#######", "#hhhhh#", "#h#h#h#", "#hhshh#", "#######"])
    assert cues.hub_thresholds(room) == {Position(3, 3)}


def test_the_start_is_always_a_threshold():
    assert cues.hub_thresholds(chamber(["###", "#s#", "###"])) == {Position(1, 1)}


def test_shipped_chambers_keep_thresholds_and_a_calm_interior():
    for number in range(1, 7):
        room = load(resource_path("levels", f"chamber_{number:02}.json"))
        edge = cues.hub_thresholds(room)
        assert room.start in edge
        assert edge <= room.hub
        assert room.hub - edge
