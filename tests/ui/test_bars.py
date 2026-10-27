"""The bars read the action model, and clicking a button equals pressing its key."""

from dataclasses import replace

import pytest

from echo_shift.engine.loader import load
from echo_shift.engine.model import Phase, Position, initial_state
from echo_shift.paths import resource_path
from echo_shift.ui import controls
from echo_shift.ui.hud import next_step


def play(player, level=3):
    player.game.open_level(level)
    player.game.modal = None
    return player.game


def run(player, steps):
    """steps: ("key", name) or ("button", action id)."""
    for kind, name in steps:
        (player.press if kind == "key" else player.button)(name)


def trace(game):
    return (
        game.state,
        game.pending,
        game.console,
        game.paused,
        game.modal,
        len(game.history),
        game.message,
    )


SEQUENCES = {
    "refused wait": ([("key", "SPACE")], [("button", "wait")]),
    "record save launch": (
        [("key", "RETURN"), ("key", "RETURN"), ("key", "RETURN")],
        [("button", "echo"), ("button", "echo"), ("button", "echo")],
    ),
    "console": ([("key", "E")], [("button", "console")]),
    "undo empty": ([("key", "Z")], [("button", "undo")]),
    "restart": ([("key", "C")], [("button", "restart")]),
    "pause": ([("key", "P")], [("button", "pause")]),
    "guide": ([("key", "T")], [("button", "guide")]),
    "hint": ([("key", "H")], [("button", "hint")]),
    "retry refused": ([("key", "R")], [("button", "retry")]),
    "rerecord refused": ([], [("button", "rerecord")]),
    "record then undo": (
        [("key", "RETURN"), ("key", "Z")],
        [("button", "echo"), ("button", "undo")],
    ),
}


@pytest.mark.parametrize("name", SEQUENCES)
def test_button_click_equals_key_press(player, name):
    keys, buttons = SEQUENCES[name]
    game = play(player)
    run(player, keys)
    by_key = trace(game)
    game = play(player)
    run(player, buttons)
    by_button = trace(game)
    if name == "rerecord refused":
        assert by_button[0] == game.state and "RECORDING" in by_button[-1]
    else:
        assert by_button == by_key


def test_disabled_button_shows_its_reason_like_its_key(player):
    game = play(player)
    reason = controls.find(game.play_actions(), "wait").reason
    player.button("wait")
    assert game.message == reason.upper()
    assert game.attempt.disabled_presses == {"wait": 1}


def test_power_chip_and_meter_open_the_console_only_at_the_console(player):
    game = play(player)
    game.draw()
    for key in ("power", "circuit:lift-power"):
        game.console = False
        player.click(next(r for r, hit in game.ui_hits if hit == key))
        assert game.console
    game.console = False
    game.state = replace(game.state, player=Position(12, 6))
    player.click(next(r for r, hit in game.ui_hits if hit == "power"))
    assert not game.console
    assert game.message == controls.find(game.play_actions(), "console").reason.upper()


def test_next_step_prefers_a_lesson_then_the_echo_key():
    state = initial_state(load(resource_path("levels", "chamber_01.json")))
    actions = controls.available_actions(state, "game", None)
    assert next_step(actions, "Do the thing") == "Do the thing"
    assert state.phase is Phase.PREPARE
    assert next_step(actions).startswith("Enter Record")


def full_take(player):
    """Free play in chamber 2 with a recording that has reached its limit."""
    game = play(player, 2)
    player.press("RETURN")
    for _ in range(game.state.chamber.max_turns):
        player.press("SPACE")
    assert len(game.state.recording) == game.state.chamber.max_turns
    return game


def assert_refused(game, action_id, before):
    reason = controls.find(game.play_actions(), action_id).reason
    assert reason == "Recording full; Enter saves it"
    assert game.message == reason.upper() and game.message_error
    assert (game.state, len(game.history)) == before
    assert game.attempt.disabled_presses == {action_id: 1}


@pytest.mark.parametrize("key", ["UP", "DOWN", "LEFT", "RIGHT", "SPACE"])
def test_a_full_recording_refuses_keys_in_place(player, key):
    game = full_take(player)
    before = (game.state, len(game.history))
    player.press(key)
    action_id = "wait" if key == "SPACE" else "move_" + key.lower()
    assert_refused(game, action_id, before)
    assert game.failure is None
    player.press("RETURN")  # the save key still works
    assert game.state.phase is Phase.COMMITTED


@pytest.mark.parametrize("action_id", ["move_up", "move_right", "wait"])
def test_a_full_recording_refuses_the_wait_button_and_tile_clicks(player, action_id):
    game = full_take(player)
    game.state = replace(game.state, player=Position(12, 6))  # off the console
    before = (game.state, len(game.history))
    if action_id == "wait":  # only the wait button is on the bar
        player.button(action_id)
        assert_refused(game, action_id, before)
        game.attempt.disabled_presses.clear()
    dx, dy = controls.MOVE_DELTAS.get(action_id, (0, 0))
    here = game.state.player
    player.click_tile(here.x + dx, here.y + dy)
    assert_refused(game, action_id, before)
