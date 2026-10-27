"""The scrolling camera: follow, clamp, centre, snap, hit-testing and markers."""

from dataclasses import replace
from pathlib import Path

from echo_shift.engine.model import (
    Chamber,
    Circuit,
    Device,
    Pad,
    Position,
    TileType,
    initial_state,
)
from echo_shift.ui import camera, cues, pointer
from echo_shift.ui.camera import Camera
from echo_shift.ui.layout import Layout, framed_bounds

WORLD = (0, 0, 29, 13)  # 30 x 14 tiles
SIZE = (16.0, 7.0)


def settle(cam, focus, size=SIZE, world=WORLD, key="k", frames=200):
    """Walk the focus there a half tile per frame, then let the camera settle."""
    while cam.focus is not None and cam.focus != focus:
        dx, dy = focus[0] - cam.focus[0], focus[1] - cam.focus[1]
        step = min(1.0, (dx * dx + dy * dy) ** 0.5) / max(
            1e-9, (dx * dx + dy * dy) ** 0.5
        )
        near = (dx * dx + dy * dy) ** 0.5 <= 0.5
        at = (
            focus
            if near
            else (cam.focus[0] + dx * step / 2, cam.focus[1] + dy * step / 2)
        )
        cam.follow(at, size, world, key)
    for _ in range(frames):
        cam.follow(focus, size, world, key)
    return cam


def big_chamber(columns=24, rows=16, pad=None, elevator=None):
    """A walled hall with devices far from the start, bigger than any view."""
    tiles = [
        [
            TileType.WALL
            if x in (0, columns - 1) or y in (0, rows - 1)
            else TileType.FLOOR
            for x in range(columns)
        ]
        for y in range(rows)
    ]
    start = Position(2, 2)
    far = pad or Position(columns - 3, rows - 3)
    lift = elevator or Position(columns - 3, 2)
    tiles[start.y][start.x] = TileType.HUB
    return Chamber(
        tiles=tuple(tuple(row) for row in tiles),
        start=start,
        hub=frozenset({start}),
        consoles=frozenset({start}),
        capacity=2,
        circuits=(Circuit("c", 1, devices=("g", "e")),),
        pads=(Pad("p", far),),
        devices=(
            Device("g", TileType.GATE, Position(4, 2), "c", "p"),
            Device("e", TileType.ELEVATOR, lift, "c", "p"),
        ),
        exit=lift,
    )


# --- follow ---------------------------------------------------------------


def test_first_frame_centres_on_the_player_clamped_to_the_world():
    cam = Camera()
    assert cam.follow((15.5, 7.5), SIZE, WORLD, "k") == (7.5, 4.0)
    cam.reset()
    assert cam.follow((0.5, 0.5), SIZE, WORLD, "k") == (0.0, 0.0)
    cam.reset()
    assert cam.follow((29.5, 13.5), SIZE, WORLD, "k") == (14.0, 7.0)


def walk(cam, start, end, frames=1):
    """Move the focus from `start` to `end` in steps of at most half a tile."""
    steps = max(1, int(abs(end - start) / 0.5) + 1)
    for step in range(1, steps + 1):
        for _ in range(frames):
            cam.follow((start + (end - start) * step / steps, 7.5), SIZE, WORLD, "k")


def test_the_player_moves_inside_the_dead_zone_without_scrolling():
    cam = Camera()
    cam.follow((15.5, 7.5), SIZE, WORLD, "k")
    start = (cam.x, cam.y)
    half = SIZE[0] * camera.DEAD_ZONE / 2
    middle = cam.x + SIZE[0] / 2
    walk(cam, 15.5, middle - half + 0.01)
    assert (cam.x, cam.y) == start
    walk(cam, middle - half + 0.01, middle + half - 0.01)
    assert (cam.x, cam.y) == start


def test_leaving_the_dead_zone_scrolls_towards_the_player():
    half = SIZE[0] * camera.DEAD_ZONE / 2
    cam = Camera()
    cam.follow((15.5, 7.5), SIZE, WORLD, "k")
    start = cam.x
    edge = start + SIZE[0] / 2 + half
    walk(cam, 15.5, edge + 1.0)
    assert start < cam.x < start + 1.0  # eased: still catching up
    back = Camera()
    back.follow((15.5, 7.5), SIZE, WORLD, "k")
    walk(back, 15.5, start + SIZE[0] / 2 - half - 1.0)
    assert back.x < start


def test_eased_follow_converges_and_ends_exactly_on_the_target():
    cam = Camera()
    cam.follow((8.5, 3.5), SIZE, WORLD, "k")
    walk(cam, 8.5, 20.5)
    half = SIZE[0] * camera.DEAD_ZONE / 2
    target = 20.5 - half - SIZE[0] / 2
    xs = []
    for _ in range(300):
        cam.follow((20.5, 7.5), SIZE, WORLD, "k")
        xs.append(cam.x)
    assert cam.x == target
    assert xs == sorted(xs)  # never overshoots or oscillates
    assert xs.index(target) < 60  # settles within a second at 60 fps


def test_reduced_motion_jumps_to_the_target_in_one_frame():
    reduced, eased = Camera(), Camera()
    for focus in range(8, 15):
        for cam, flag in ((reduced, True), (eased, False)):
            cam.follow((focus + 0.5, 3.5), SIZE, WORLD, "k", reduced=flag)
    target = 14.5 - SIZE[0] * camera.DEAD_ZONE / 2 - SIZE[0] / 2
    assert reduced.x == target  # always exactly where the dead zone asks
    assert eased.x < target  # the eased camera is still catching up


def test_the_view_never_leaves_the_world():
    cam = Camera()
    for focus in ((0.5, 0.5), (29.5, 0.5), (0.5, 13.5), (29.5, 13.5), (15.5, 7.5)):
        settle(cam, focus)
        assert 0 <= cam.x <= WORLD[2] + 1 - SIZE[0]
        assert 0 <= cam.y <= WORLD[3] + 1 - SIZE[1]


def test_a_world_smaller_than_the_view_is_centred_and_never_scrolls():
    world = (3, 2, 9, 5)  # 7 x 4 tiles
    cam = Camera()
    shown = cam.follow((4.5, 3.5), SIZE, world, "k")
    assert shown == (3 - (16 - 7) / 2, 2 - (7 - 4) / 2)
    for focus in ((3.5, 2.5), (9.5, 5.5), (6.5, 4.0)):
        cam.follow(focus, SIZE, world, "k")
        assert (cam.x, cam.y) == shown


def test_a_narrower_view_scrolls_where_a_wide_one_did_not():
    world = (0, 0, 11, 6)  # 12 x 7: fits 16 wide, not 8 wide
    wide, narrow = Camera(), Camera()
    wide.follow((1.5, 3.5), (16.0, 7.0), world, "k")
    settle(wide, (11.5, 3.5), (16.0, 7.0), world)
    assert wide.x == -2.0
    narrow.follow((1.5, 3.5), (8.0, 7.0), world, "k")
    settle(narrow, (11.5, 3.5), (8.0, 7.0), world)
    assert narrow.x == 4.0  # right edge of the world
    assert narrow.x <= 11.5 - 0.5 < narrow.x + 8.0  # the player stays visible


def test_a_teleport_snaps_but_a_step_does_not():
    cam = Camera()
    settle(cam, (5.5, 3.5))
    cam.follow((6.5, 3.5), SIZE, WORLD, "k")  # one tile: follows normally
    before = cam.x
    cam.follow((25.5, 10.5), SIZE, WORLD, "k")  # undo or retry jump
    assert (cam.x, cam.y) == (14.0, 7.0) and cam.x != before


def test_a_new_key_or_a_reset_snaps():
    cam = Camera()
    settle(cam, (5.5, 3.5))
    assert cam.follow((5.5, 3.5), SIZE, WORLD, "other") == (0.0, 0.0)
    cam.follow((20.5, 3.5), SIZE, WORLD, "other")
    cam.reset()
    assert cam.follow((20.5, 3.5), SIZE, WORLD, "other") == (12.5, 0.0)


def test_camera_module_never_imports_pyxel():
    assert "pyxel" not in Path(camera.__file__).read_text(encoding="utf-8")


# --- view geometry and hit-testing ----------------------------------------


def cell_for(layout, bounds):
    return layout.tile_size(bounds[2] - bounds[0] + 1, bounds[3] - bounds[1] + 1)


def scrolled_view(layout=None, console=False):
    layout = layout or Layout.fit(1280, 720)
    chamber = big_chamber()
    bounds = framed_bounds(chamber)
    port = layout.room_viewport(console)
    cell = cell_for(layout, bounds)
    cam = Camera()
    cam.follow(
        (20.5, 10.5), (port[2] / cell, port[3] / cell), bounds, "k"
    )  # near the far corner
    return layout, (cell, *camera.view_origin(port, cell, (cam.x, cam.y))), bounds


def test_the_big_chamber_scrolls_at_every_window_size():
    for size in ((640, 480), (1280, 720), (1920, 1080)):
        layout = Layout.fit(*size)
        _, (cell, ox, _), bounds = scrolled_view(layout)
        assert ox + bounds[0] * cell < layout.room[0]  # left part is scrolled away
        assert ox + (bounds[2] + 1) * cell >= layout.room[0] + layout.room[2]


def test_every_visible_pixel_maps_to_the_tile_drawn_there():
    layout, view, bounds = scrolled_view()
    cell, ox, oy = view
    rx, ry, rw, rh = layout.room
    for x in range(rx, rx + rw, 7):
        for y in range(ry, ry + rh, 7):
            found = pointer.tile_at(view, bounds, layout.room, x, y)
            assert found == Position((x - ox) // cell, (y - oy) // cell)
            assert bounds[0] <= found.x <= bounds[2]
            assert bounds[1] <= found.y <= bounds[3]
            left, top, _, _ = camera.tile_rect(view, found.x, found.y)
            assert left <= x < left + cell and top <= y < top + cell


def test_tiles_outside_the_view_cannot_be_clicked():
    layout, view, bounds = scrolled_view()
    hidden = Position(bounds[0] + 1, bounds[1] + 1)
    x, y, w, h = camera.tile_rect(view, hidden.x, hidden.y)
    assert not camera.visible(view, layout.room, hidden.x, hidden.y)
    assert pointer.tile_at(view, bounds, layout.room, x + w // 2, y + h // 2) is None
    assert camera.visible_tiles(view, layout.room, bounds) is not None
    seen = camera.visible_tiles(view, layout.room, bounds)
    assert seen[0] > bounds[0] and seen[2] == bounds[2]
    # Every pixel of the room hits one of the visible tiles, none of the others.
    hits = {
        pointer.tile_at(view, bounds, layout.room, x, y)
        for x in range(layout.room[0], layout.room[0] + layout.room[2], 5)
        for y in range(layout.room[1], layout.room[1] + layout.room[3], 5)
    }
    assert all(seen[0] <= t.x <= seen[2] and seen[1] <= t.y <= seen[3] for t in hits)


def test_the_drawer_still_hides_tiles_under_a_scrolled_camera():
    layout, view, bounds = scrolled_view(console=True)
    drawer_x = layout.console_drawer()[0]
    y = layout.room_y + layout.room_h // 2
    x = drawer_x - layout.pad - view[0] // 2  # inside the last visible column
    tile = pointer.tile_at(view, bounds, layout.room, x, y)
    assert tile is not None
    assert pointer.tile_at(view, bounds, layout.room, x, y, drawer_x) == tile
    assert pointer.tile_at(view, bounds, layout.room, x, y, x) is None  # covered
    assert pointer.tile_at(view, bounds, layout.room, drawer_x, y, drawer_x) is None


def test_the_framed_edge_is_where_the_world_ends_even_when_centred():
    layout = Layout.fit(1280, 720)
    chamber = big_chamber(columns=8, rows=6)
    bounds = framed_bounds(chamber)
    port = layout.room_viewport()
    cam = Camera()
    cell = cell_for(layout, bounds)
    cam.follow((3.5, 3.5), (port[2] / cell, port[3] / cell), bounds, "k")
    view = (cell, *camera.view_origin(port, cell, (cam.x, cam.y)))
    left = camera.tile_rect(view, bounds[0], 0)[0]
    assert left > layout.room[0]  # centred with a margin
    assert pointer.tile_at(view, bounds, layout.room, left - 1, port[1] + 5) is None


# --- markers ----------------------------------------------------------------


def test_markers_point_at_off_screen_devices_with_their_kind():
    layout, view, _ = scrolled_view()
    state = initial_state(big_chamber())
    marks = cues.offscreen_markers(
        view, layout.room, cues.offscreen_targets(state, None), 12
    )
    kinds = {m.kind for m in marks}
    assert kinds == {"gate", "elevator"}  # the pad is in view, those two are not
    gate = next(m for m in marks if m.kind == "gate")
    assert gate.dx < 0  # points left, towards the gate
    lift = next(m for m in marks if m.kind == "elevator")
    assert lift.dy < 0  # and up, towards the elevator
    rx, ry, rw, rh = layout.room
    assert rx <= gate.x <= rx + rw and ry <= gate.y <= ry + rh


def test_the_echo_gets_a_marker_when_it_is_out_of_sight():
    layout, view, _ = scrolled_view()
    state = initial_state(big_chamber())
    marks = cues.offscreen_markers(
        view, layout.room, cues.offscreen_targets(state, (2.0, 2.0, None)), 12
    )
    assert any(m.kind == "echo" and m.dx < 0 for m in marks)


def test_markers_stay_quiet_when_everything_is_visible():
    layout = Layout.fit(1280, 720)
    chamber = big_chamber(
        columns=8, rows=6, pad=Position(5, 4), elevator=Position(5, 2)
    )
    bounds = framed_bounds(chamber)
    port = layout.room_viewport()
    cell = cell_for(layout, bounds)
    cam = Camera()
    cam.follow((3.5, 3.5), (port[2] / cell, port[3] / cell), bounds, "k")
    view = (cell, *camera.view_origin(port, cell, (cam.x, cam.y)))
    targets = cues.offscreen_targets(initial_state(chamber), (2.0, 2.0, None))
    assert len(targets) == 4  # a pad, a gate, an elevator and the echo
    assert cues.offscreen_markers(view, layout.room, targets, 12) == ()


def test_edge_marker_sits_on_the_inset_edge_towards_the_target():
    rect = (0, 100, 400, 200)
    found = camera.edge_marker(rect, (1000.0, 200.0), 10)
    assert found is not None
    (x, y), (dx, dy) = found
    assert (x, y) == (390.0, 200.0) and (dx, dy) == (1.0, 0.0)
    (x, y), (dx, dy) = camera.edge_marker(rect, (-300.0, -300.0), 10)
    assert 10 <= x <= 390 and 110 <= y <= 290 and dx < 0 and dy < 0
    assert camera.edge_marker(rect, (200.0, 200.0), 10) is None


def test_a_link_line_leaves_the_room_edge_where_it_crosses():
    rect = (0, 0, 100, 100)
    assert camera.exit_point(rect, (50.0, 50.0), (150.0, 50.0)) == (100.0, 50.0)
    assert camera.exit_point(rect, (50.0, 50.0), (60.0, 60.0)) is None


# --- through the game ---------------------------------------------------------


def test_the_game_scrolls_with_the_player_and_clicks_use_the_drawn_view(player):
    game = player.game
    game.open_level(1)
    chamber = big_chamber()
    game.state = initial_state(chamber)
    game.modal = None
    game.camera.reset()
    game.draw()
    first = game.room_view
    assert game.layout.min_tile == first[0]  # too big to fit: the smallest tile
    assert game.pointer_tile(first) is None  # pointer starts off the room
    for x in range(2, 21):
        game.state = replace(game.state, player=Position(x, 8))
        for _ in range(200):
            game.draw()
    cell, ox, oy = game.room_view
    assert game.room_view != first  # the camera followed
    room_x, room_y, room_w, room_h = game.layout.room
    px, py = ox + 20 * cell + cell // 2, oy + 8 * cell + cell // 2
    assert room_x <= px < room_x + room_w and room_y <= py < room_y + room_h
    player.fake.mouse_x, player.fake.mouse_y = px, py
    assert game.pointer_tile(game.room_view) == Position(20, 8)
    player.fake.mouse_x = player.fake.mouse_y = -1


def test_a_small_chamber_zooms_to_fit_and_never_scrolls(player):
    game = player.game
    game.open_level(1)
    game.modal = None
    game.state = initial_state(big_chamber(columns=8, rows=6))
    game.camera.reset()
    bounds = framed_bounds(game.state.chamber)
    for _ in range(3):
        game.draw()
    cell, ox, oy = game.room_view
    assert cell == game.layout.tile_size(
        bounds[2] - bounds[0] + 1, bounds[3] - bounds[1] + 1
    )
    assert cell > game.layout.min_tile  # bigger than the scrolling floor
    room_x, room_y, room_w, room_h = game.layout.room
    assert ox + bounds[0] * cell >= room_x
    assert ox + (bounds[2] + 1) * cell <= room_x + room_w
    assert oy + bounds[1] * cell >= room_y
    assert oy + (bounds[3] + 1) * cell <= room_y + room_h
    before = game.room_view
    game.state = replace(game.state, player=Position(bounds[2] - 1, bounds[3] - 1))
    for _ in range(100):
        game.draw()
    assert game.room_view == before  # the whole chamber is in view: nothing moves


def test_the_cap_stops_a_tiny_chamber_from_blowing_up():
    layout = Layout.fit(1280, 720)
    assert layout.tile_size(1, 1) == 2 * layout.cell
