"""Mouse play: tile hit-testing, click actions and keyboard equivalence."""

import json
from dataclasses import replace

import pytest

from echo_shift.engine.loader import load
from echo_shift.engine.model import Phase, Position, initial_state
from echo_shift.engine.recording import enter
from echo_shift.engine.turn import Wait
from echo_shift.paths import resource_path
from echo_shift.ui import controls, pointer
from echo_shift.ui.layout import Layout, framed_bounds

SIZES = [(640, 480), (1280, 720), (1536, 864), (1920, 1080)]
ARROWS = {
    "move_up": "UP",
    "move_down": "DOWN",
    "move_left": "LEFT",
    "move_right": "RIGHT",
}


def chamber_state(number=3):
    return initial_state(load(resource_path("levels", f"chamber_{number:02}.json")))


def fitted(width, height, number=3, console=False):
    chamber = chamber_state(number).chamber
    bounds = framed_bounds(chamber)
    columns, rows = bounds[2] - bounds[0] + 1, bounds[3] - bounds[1] + 1
    layout = Layout.fit(width, height)
    cell, fit_x, fit_y = layout.room_fit(columns, rows, console)
    view = (cell, fit_x - bounds[0] * cell, fit_y - bounds[1] * cell)
    return layout, view, bounds


@pytest.mark.parametrize(("width", "height"), SIZES)
def test_every_pixel_of_a_cell_maps_to_that_tile(width, height):
    layout, (cell, ox, oy), bounds = fitted(width, height)
    assert cell > 1
    for x in range(bounds[0], bounds[2] + 1):
        for y in range(bounds[1], bounds[3] + 1):
            for dx, dy in ((0, 0), (cell - 1, 0), (0, cell - 1), (cell - 1, cell - 1)):
                found = pointer.tile_at(
                    (cell, ox, oy),
                    bounds,
                    layout.room,
                    ox + x * cell + dx,
                    oy + y * cell + dy,
                )
                assert found == Position(x, y), (width, height, x, y, dx, dy)


@pytest.mark.parametrize(("width", "height"), SIZES)
def test_pixels_beyond_the_drawn_tiles_and_the_room_hit_nothing(width, height):
    layout, view, bounds = fitted(width, height)
    cell, ox, oy = view
    room_x, room_y, room_w, room_h = layout.room

    def at(x, y):
        return pointer.tile_at(view, bounds, layout.room, x, y)

    assert at(ox + (bounds[0]) * cell - 1, oy + bounds[1] * cell) is None
    assert at(ox + (bounds[2] + 1) * cell, oy + bounds[1] * cell) is None
    assert at(ox + bounds[0] * cell, oy + (bounds[3] + 1) * cell) is None
    # The bars sit above and below the room band and never hit a tile.
    assert at(room_x + room_w // 2, room_y - 1) is None
    assert at(room_x + room_w // 2, room_y + room_h) is None
    assert at(-1, room_y + 1) is None
    assert at(room_x + room_w, room_y + 1) is None
    assert at(layout.width // 2, layout.height - 1) is None
    assert at(layout.width // 2, 0) is None


@pytest.mark.parametrize(("width", "height"), SIZES)
def test_the_console_drawer_hides_the_tiles_under_it(width, height):
    layout, view, bounds = fitted(width, height, console=True)
    cell, ox, oy = view
    drawer_x = layout.console_drawer()[0]
    tile = Position(bounds[2], bounds[1] + 1)
    x, y = ox + tile.x * cell + cell // 2, oy + tile.y * cell + cell // 2
    assert pointer.tile_at(view, bounds, layout.room, x, y, None) == tile
    assert x < drawer_x  # the fit keeps every tile left of the drawer
    assert pointer.tile_at(view, bounds, layout.room, drawer_x, y, drawer_x) is None


def test_click_actions_match_the_arrow_keys():
    state = replace(chamber_state(), player=Position(4, 4))
    for action_id, (dx, dy) in controls.MOVE_DELTAS.items():
        target = Position(4 + dx, 4 + dy)
        assert pointer.click_action(state, target) == action_id


def test_the_own_tile_waits_and_the_console_tile_opens_the_console():
    state = chamber_state()
    on_console = state.player
    assert on_console in state.chamber.consoles
    assert pointer.click_action(state, on_console) == "console"
    away = replace(state, player=Position(4, 4))
    assert pointer.click_action(away, Position(4, 4)) == "wait"
    far = replace(state, player=Position(5, 4))
    assert pointer.click_action(far, on_console) == "console"  # shows its reason
    assert pointer.click_action(replace(far, player=Position(4, 4)), on_console) == (
        "move_left"
    )


def test_non_adjacent_tiles_map_to_nothing():
    state = replace(chamber_state(), player=Position(4, 4))
    for target in (
        Position(5, 5),  # diagonal
        Position(3, 3),
        Position(6, 4),  # two away
        Position(4, 6),
        Position(0, 0),  # a wall far off
        Position(11, 8),
    ):
        assert pointer.click_action(state, target) is None, target


def test_hover_outlines_only_actionable_targets():
    state = chamber_state()
    actions = controls.available_actions(state, "game", None)
    here = state.player
    assert pointer.hover_action(state, here, actions) == "console"
    assert pointer.hover_action(state, Position(4, 4), actions) == "move_right"
    assert pointer.hover_action(state, Position(3, 3), actions) is None  # wall
    assert pointer.hover_action(state, Position(7, 4), actions) is None  # far
    away = replace(state, player=Position(4, 4))
    away_actions = controls.available_actions(away, "game", None)
    assert pointer.hover_action(away, away.player, away_actions) is None  # no wait yet
    assert pointer.hover_action(away, here, away_actions) == "move_left"
    recording = replace(away, phase=Phase.RECORDING)
    live = controls.available_actions(recording, "game", None)
    assert pointer.hover_action(recording, recording.player, live) == "wait"
    assert pointer.hover_action(state, Position(5, 4), actions) is None  # not adjacent


# ---- the running game ----------------------------------------------------------


def start(player, number=3):
    player.game.open_level(number)
    player.press("F")
    return player.game


def lit(player, number=3):
    """Free play with the lift circuit already on, so the route is walkable."""
    game = start(player, number)
    game.pending = frozenset({"lift-power"})
    game.state = initial_state(game.state.chamber, game.pending)
    return game


def outcome(game):
    return (
        game.state.search_key(),
        game.state.turns,
        game.message,
        len(game.history),
        dict(game.attempt.disabled_presses),
        game.console,
        game.modal,
    )


@pytest.mark.parametrize("action_id", list(ARROWS))
def test_clicking_an_adjacent_tile_does_what_the_arrow_key_does(player, action_id):
    results = []
    for use_mouse in (False, True):
        game = lit(player)
        player.press("RETURN")  # record, so walls and waits have consequences
        player.press("RIGHT")
        assert game.state.player == Position(4, 4)
        dx, dy = controls.MOVE_DELTAS[action_id]
        if use_mouse:
            player.click_tile(4 + dx, 4 + dy)
        else:
            player.press(ARROWS[action_id])
        results.append(outcome(game))
    assert results[0] == results[1]


def test_clicking_the_own_tile_waits_and_a_disabled_wait_shows_its_reason(player):
    game = lit(player)
    reason = controls.find(game.play_actions(), "wait").reason
    game.state = replace(game.state, player=Position(4, 4))
    player.click_tile(4, 4)
    assert game.message == reason.upper()
    assert game.attempt.disabled_presses == {"wait": 1} and game.state.turns == 0
    game.state = replace(game.state, player=Position(3, 4))
    player.press("RETURN")
    player.press("RIGHT")
    turns = game.state.turns
    player.click_tile(4, 4)
    assert game.state.turns == turns + 1 and isinstance(game.state.recording[-1], Wait)


def test_clicking_the_console_opens_it_only_when_standing_on_it(player):
    game = lit(player)
    player.click_tile(3, 4)
    assert game.console
    player.press("ESCAPE")
    player.press("RETURN")
    player.press("RIGHT")
    player.click_tile(3, 4)  # the console is adjacent now, so this is a move
    assert not game.console and game.state.player == Position(3, 4)
    player.click_tile(4, 4)
    player.click_tile(5, 4)  # two tiles from the console
    reason = controls.find(game.play_actions(), "console").reason
    player.click_tile(3, 4)
    assert not game.console and game.state.player == Position(5, 4)
    assert game.message == reason.upper()
    assert game.attempt.disabled_presses == {"console": 1}


def test_non_adjacent_clicks_change_nothing_and_record_nothing(player):
    game = lit(player)
    player.press("RETURN")
    player.press("RIGHT")
    before = outcome(game)
    for tile in ((6, 4), (5, 3), (0, 0), (11, 8), (2, 4)):
        player.click_tile(*tile)
    player.click_at(10, game.layout.height - 4)  # the bottom bar, off any button
    player.click_at(game.layout.width - 2, game.layout.room_y + 2)  # room corner
    assert outcome(game) == before
    assert game.attempt.disabled_presses == {}


def test_mouse_is_ignored_while_an_overlay_covers_the_room(player):
    game = lit(player)
    player.press("RETURN")
    player.press("E")
    before = game.state
    player.click_tile(4, 4)
    assert game.console and game.state is before
    player.press("ESCAPE")
    assert not game.console


def test_clicks_obey_lesson_gating_like_keys(player):
    game = player.game
    game.open_level(1)
    player.press("RETURN")  # start the guided lesson
    player.press("RETURN")  # ready to try
    assert game.lesson.current.action == "open_console"
    before = game.state
    player.click_tile(4, 4)
    assert game.state is before and not game.console
    assert game.message.startswith("NEXT:")
    player.click_tile(3, 4)
    assert game.console and game.lesson.current.action != "open_console"


def test_hover_outline_is_drawn_on_actionable_tiles_only(player):
    game = start(player)
    outlines = []
    player.fake.rectb = lambda *a: outlines.append(a)
    game.draw()
    cell, ox, oy = game.room_view

    def hover(x, y):
        outlines.clear()
        player.fake.mouse_x, player.fake.mouse_y = (
            ox + x * cell + cell // 2,
            oy + y * cell + cell // 2,
        )
        game.draw()
        return [o for o in outlines if o[4] == 7 and o[2] == cell - 2]

    assert hover(4, 4) == [
        (ox + 4 * cell + 1, oy + 4 * cell + 1, cell - 2, cell - 2, 7)
    ]
    assert len(hover(3, 4)) == 1  # the console under the player
    assert hover(4, 3) == [] and hover(6, 4) == []
    player.fake.mouse_x = player.fake.mouse_y = -1


def test_right_click_closes_overlays_but_not_the_failure_card(player):
    game = start(player)
    right = player.fake.MOUSE_BUTTON_RIGHT
    player.press("E")
    player.click_at(20, 20, right)
    assert not game.console and not game.paused
    player.click_at(20, 20, right)  # plain play: right click does nothing
    assert not game.paused
    player.press("T")
    assert game.modal == "guide"
    player.click_at(20, 20, right)
    assert game.modal is None
    player.press("H")
    assert game.modal == "guide"
    player.click_at(20, 20, right)
    assert game.modal is None
    player.press("P")
    assert game.paused
    player.click_at(20, 20, right)
    assert not game.paused


def test_right_click_cannot_dismiss_the_failure_card(player):
    game = start(player, 2)
    for key in ("RETURN", "RETURN", "RETURN", "RIGHT"):
        player.press(key)
    assert game.failure is not None
    player.click_at(20, 20, player.fake.MOUSE_BUTTON_RIGHT)
    assert game.failure is not None


def test_close_is_the_only_action_bound_to_the_right_button():
    holders = [
        i for i in controls.BINDINGS if controls.RIGHT_CLICK in controls.key_names(i)
    ]
    assert holders == ["close"]
    assert "close" not in controls.SCOPES["play"]  # play ignores right-click


def failed(player):
    game = start(player, 2)
    for key in ("RETURN", "RETURN", "RETURN"):
        player.press(key)
    player.click_tile(4, 4)  # the unpowered path is dark
    assert game.failure is not None and game.failure.kind == "replay"
    return game


def test_failure_card_rows_are_clickable(player):
    game = failed(player)
    restored = game.failure.restored
    player.click_row("row:failure:retry")
    assert game.failure is None and game.state == restored
    assert game.attempt.failure_choices == {"retry": 1}
    game = failed(player)
    player.click_row("row:failure:undo")
    assert game.failure is None and game.attempt.failure_choices["undo"] == 1
    game = failed(player)
    player.click_row("row:failure:restart")
    assert game.failure is None
    assert game.state == initial_state(game.state.chamber)


def test_clicking_the_failure_card_elsewhere_changes_nothing(player):
    game = failed(player)
    player.click_at(5, 5)
    player.click_at(game.layout.width // 2, game.layout.height - 3)
    assert game.failure is not None


def test_pause_items_are_clickable_and_hovered(player):
    game = start(player, 2)
    player.press("RETURN")
    player.press("P")
    assert game.paused
    outlines = []
    player.fake.rectb = lambda *a: outlines.append(a)
    game.draw()
    rect = next(r for r, key in game.ui_hits if key == "row:pause:restart")
    player.fake.mouse_x, player.fake.mouse_y = rect[0] + 2, rect[1] + 2
    outlines.clear()
    game.draw()
    assert (*rect, 10) in outlines
    player.click_row("row:pause:undo")
    assert not game.paused and game.state.phase is Phase.PREPARE
    player.press("P")
    player.click_row("row:pause:pause")  # the first row resumes
    assert not game.paused
    player.press("P")
    player.click_row("row:pause:levels")
    assert game.mode == "levels"


def test_console_rows_select_toggle_and_apply(player):
    game = start(player, 2)
    player.click_tile(3, 4)
    assert game.console
    ids = [c.id for c in game.state.chamber.circuits]
    assert len(ids) >= 2
    player.click_row(f"row:circuit:{ids[1]}")
    assert game.selection == 1
    assert game.state.powered_circuits == frozenset({ids[1]})  # free power is instant
    player.click_row(f"row:circuit:{ids[1]}")
    assert game.state.powered_circuits == frozenset()
    player.click_row("row:apply")
    assert not game.console


def test_staged_console_changes_cost_a_turn_on_apply_click(player):
    game = start(player, 2)
    player.press("RETURN")  # record
    assert game.state.phase is Phase.RECORDING
    player.click_tile(3, 4)
    first = game.state.chamber.circuits[0].id
    player.click_row(f"row:circuit:{first}")
    assert first in game.pending and game.state.powered_circuits == frozenset()
    turns = game.state.turns
    player.click_row("row:apply")
    assert game.state.turns == turns + 1 and first in game.state.powered_circuits
    assert not game.console


def test_guide_and_result_have_clickable_controls(player):
    game = start(player, 1)
    player.press("T")
    player.click_row("row:guide:close")
    assert game.modal is None
    player.press("H")
    assert game.modal == "guide"
    player.click_row("row:guide:close")
    assert game.modal is None
    game.modal = "result"
    player.click_row("row:result:close")
    assert game.mode == "levels"


# ---- keyboard and mouse solve the chambers identically ---------------------------

DIRECTION_KEYS = {"up": "UP", "right": "RIGHT", "down": "DOWN", "left": "LEFT"}
DIRECTION_STEPS = {"up": (0, -1), "right": (1, 0), "down": (0, 1), "left": (-1, 0)}


def solution(number):
    path = resource_path("levels", "solutions", f"chamber_{number:02}.json")
    return json.loads(path.read_text())["steps"]


def key_step(player, token):
    game = player.game
    if isinstance(token, dict):
        player.press("E")
        wanted = set(token["power"])
        for index, circuit in enumerate(game.state.chamber.circuits):
            while game.selection < index:
                player.press("DOWN")
            if (circuit.id in wanted) != (circuit.id in game.pending):
                player.press("SPACE")
        player.press("RETURN")
    elif token in DIRECTION_KEYS:
        player.press(DIRECTION_KEYS[token])
    elif token == "wait":
        player.press("SPACE")
    else:
        player.press("RETURN")


def mouse_step(player, token):
    game = player.game
    here = game.state.player
    if isinstance(token, dict):
        player.click_tile(here.x, here.y)
        wanted = set(token["power"])
        for circuit in game.state.chamber.circuits:
            if (circuit.id in wanted) != (circuit.id in game.pending):
                player.click_row(f"row:circuit:{circuit.id}")
        player.click_row("row:apply")
    elif token in DIRECTION_STEPS:
        dx, dy = DIRECTION_STEPS[token]
        player.click_tile(here.x + dx, here.y + dy)
    elif token == "wait":
        player.click_tile(here.x, here.y)
    else:
        player.button("echo")


def play(player, number, mouse):
    game = player.game
    game.open_level(number)
    if mouse:
        game.draw()
        player.click(game.choice_hits[1])  # Play freely
    else:
        player.press("F")
    assert game.attempt.mode == "free"
    trace = []
    for token in solution(number):
        (mouse_step if mouse else key_step)(player, token)
        assert game.failure is None
        trace.append((game.state.search_key(), game.state.turns, game.state.phase))
    assert game.modal == "result"
    return trace


def telemetry(player):
    path = player.directory / "playtest.jsonl"
    keep = ("chamber", "mode", "completed", "resets", "hints", "unsafe_power_choices")
    keep += ("undos", "disabled_presses", "failure_choices", "previews")
    return [
        {k: record[k] for k in keep}
        for record in map(json.loads, path.read_text().splitlines())
    ]


@pytest.mark.parametrize("number", [1, 2, 3, 4, 5, 6])
def test_keyboard_and_mouse_play_identical_engine_sequences(player, number):
    by_keys = play(player, number, mouse=False)
    by_keys_log = telemetry(player)
    by_mouse = play(player, number, mouse=True)
    assert by_keys == by_mouse
    assert by_keys[-1][2] is Phase.RESULT
    log = telemetry(player)
    assert len(log) == len(by_keys_log) + 1
    assert log[-1] == by_keys_log[-1]
    assert log[-1]["completed"] and log[-1]["disabled_presses"] == {}


def test_mouse_play_uses_the_same_history_as_keys(player):
    game = start(player, 1)
    for key in ("E", "SPACE", "RETURN", "RETURN"):
        player.press(key)
    assert game.state.phase is Phase.RECORDING
    by_keys = (len(game.history), game.state.search_key())
    game = start(player, 1)
    player.click_tile(3, 4)
    player.click_row("row:circuit:lift-power")
    player.click_row("row:apply")
    player.button("echo")
    assert (len(game.history), game.state.search_key()) == by_keys
    player.button("undo")
    assert game.state.phase is Phase.PREPARE and game.attempt.undos == 1
    assert enter(game.state).phase is Phase.RECORDING
