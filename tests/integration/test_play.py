"""Failure and undo, the console drawer, the mouse, pause and the guide."""

from dataclasses import replace

import pytest

from echo_shift.engine.model import Phase, Position, TileType
from echo_shift.ui import guide, progress

from .conftest import assert_bars_intact, room_extent

pytestmark = pytest.mark.pyxel


def start(real, number):
    """Open a chamber and choose free play."""
    real.game.open_level(number)
    real.frame()
    real.press("F")
    assert real.game.modal is None and real.game.lesson is None
    return real.game


def snap(game):
    return game.state.search_key(), game.pending, game.console


def test_undo_returns_to_the_state_before_a_failure(real):
    game = start(real, 2)
    for _ in range(3):
        real.press("RETURN")  # record, save, launch
    assert game.state.phase is Phase.REPLAY
    before = snap(game)
    real.press("RIGHT")  # the route is dark
    assert game.failure is not None and game.failure.kind == "replay"
    assert snap(game) == before  # the card is shown first; nothing is applied yet
    real.frame()
    # The failure card is a panel over the room: the bars around it stay whole.
    assert_bars_intact(real)
    real.press("Z")
    assert game.failure is None
    assert snap(game) == before
    assert game.attempt.failure_choices == {"undo": 1}


def test_console_drawer_opens_toggles_applies_and_closes(real):
    game = start(real, 2)
    room_before = room_extent(game)
    real.press("E")
    assert game.console
    for _ in range(60):
        real.frame()  # the camera eases the room over
    drawer_x, drawer_y, drawer_w, drawer_h = game.layout.console_drawer()
    # The camera keeps the player left of the drawer; the strip is not room art.
    cell, origin_x, _ = game.room_view
    assert origin_x + (game.state.player.x + 1) * cell <= drawer_x
    assert real.pixel(drawer_x + drawer_w // 2, drawer_y + drawer_h - 2) == 1
    assert_bars_intact(real)
    circuit = game.state.chamber.circuits[game.selection].id
    real.press("SPACE")  # toggle the selected circuit
    assert circuit in game.pending
    real.press("E")  # Escape and E both close it
    assert not game.console
    assert game.state.powered_circuits == game.pending  # prepare applies at once
    for _ in range(60):
        real.frame()
    assert room_extent(game) == room_before


def test_console_apply_costs_a_turn_while_recording(real):
    game = start(real, 2)
    real.press("RETURN")  # record
    assert game.state.phase is Phase.RECORDING
    real.press("E")
    assert game.console
    real.press("SPACE")
    assert game.state.powered_circuits != game.pending  # staged until applied
    staged, turns = snap(game), game.state.turns
    real.press("RETURN")  # apply
    assert not game.console
    assert game.state.powered_circuits == game.pending
    assert game.state.turns == turns + 1
    real.press("Z")
    assert snap(game) == staged and game.console


def test_mouse_tile_click_moves_like_the_arrow_key(real):
    game = start(real, 1)
    real.press("E")
    real.press("SPACE")
    real.press("RETURN")
    real.press("RETURN")  # record
    start_tile = game.state.player
    real.click_tile(start_tile.x + 1, start_tile.y)
    assert game.state.player == Position(start_tile.x + 1, start_tile.y)
    assert len(game.state.recording) == 1
    real.click_tile(start_tile.x + 3, start_tile.y)  # not adjacent: nothing
    assert len(game.state.recording) == 1


def test_bar_button_and_undo_button_by_mouse(real):
    game = start(real, 1)
    real.press("RETURN")  # record
    real.click_key("action:wait")
    assert len(game.state.recording) == 1
    real.click_key("action:undo")
    assert len(game.state.recording) == 0
    assert game.attempt.undos == 1


def test_pause_menu_items_by_mouse_and_right_click(real):
    game = start(real, 1)
    real.press("ESCAPE")
    assert game.paused
    real.frame()
    assert_bars_intact(real)
    real.click_key("row:pause:settings")
    assert game.settings_open
    before = game.progress.settings.mute
    real.click_key("row:setting:mute")
    assert game.progress.settings.mute is not before
    assert progress.load(3).settings.mute is not before  # saved at once
    real.click_key("row:setting:close")
    assert not game.settings_open and game.paused
    real.click_key("row:pause:pause")  # the first row resumes
    assert not game.paused
    real.press("ESCAPE")
    real.click_at(10, 10, "RIGHT")
    assert not game.paused


def test_pause_by_keyboard_and_resume(real):
    game = start(real, 1)
    real.press("P")
    assert game.paused
    real.press("DOWN")
    assert game.pause_index == 1
    real.press("P")
    assert not game.paused


def test_guide_opens_pages_by_key_and_mouse_and_closes(real):
    game = start(real, 1)
    real.press("T")
    assert game.modal == "guide" and game.guide_page == guide.PAGE_IDS.index("goal")
    real.press("RIGHT")
    assert game.guide_page == 1
    real.press("LEFT")
    assert game.guide_page == 0
    real.frame()
    real.click_key("row:guide:next")
    assert game.guide_page == 1
    real.press("ESCAPE")
    assert game.modal is None and not game.paused
    # Gameplay keys are held back until released, then work again.
    real.press("RETURN")
    assert game.state.phase is Phase.RECORDING


def test_room_art_fills_the_room_band_and_the_bars_stay_clear(real):
    game = start(real, 3)
    real.frame()
    assert_bars_intact(real)
    layout = game.layout
    left, top, width, height = layout.room
    colours = {
        real.pixel(x, y)
        for x in range(left, left + width, 5)
        for y in range(top, top + height, 5)
    }
    assert len(colours) >= 3  # tiles, not an empty panel
    # The bars cover the whole width, so no room art can sit beside them.
    for rect in (layout.top, layout.bottom):
        _, y, w, h = rect
        assert {real.pixel(x, y + h // 2) for x in (0, w - 1)} == {1}


def test_a_chamber_bigger_than_the_room_scrolls_and_keeps_the_bars_whole(real):
    game = start(real, 2)
    chamber = game.state.chamber
    floor = (TileType.FLOOR,) * 14
    tiles = tuple(row + floor for row in chamber.tiles) + (floor + floor[:12],) * 10
    tiles = tuple(row + (TileType.FLOOR,) * (26 - len(row)) for row in tiles)
    wide = replace(chamber, tiles=tiles)
    far = Position(24, 17)
    game.state = replace(game.state, chamber=wide, player=far)
    game.camera.reset()
    real.frame()
    cell, origin_x, origin_y = game.room_view
    assert cell == game.layout.min_tile
    left, top, _, _ = room_extent(game)
    assert left < game.layout.room_x and top < game.layout.room_y  # scrolled away
    assert origin_x + far.x * cell < game.layout.room_x + game.layout.room_w
    # Gates and pads far behind the camera get edge arrows without painting the bars.
    assert_bars_intact(real)
    click_x = origin_x + far.x * cell + cell // 2
    click_y = origin_y + far.y * cell + cell // 2
    assert game.pointer_tile(game.room_view) is None  # the pointer is off the room
    real.click_at(click_x, click_y)  # the player's own tile waits
    assert game.state.phase is Phase.PREPARE
