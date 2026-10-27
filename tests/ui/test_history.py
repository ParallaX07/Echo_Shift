"""Undo restores earlier states exactly and never calls the engine."""

from dataclasses import replace

import pytest

from echo_shift.engine.loader import load
from echo_shift.engine.model import Position, initial_state
from echo_shift.paths import resource_path
from echo_shift.ui import app, controls
from echo_shift.ui.history import History, Snapshot


def snap(game):
    return game.snapshot()


def undoes(player, key):
    """Press `key`, expect a change, undo it and expect the exact previous state."""
    game = player.game
    before = snap(game)
    player.press(key)
    after = snap(game)
    assert after != before, key
    player.press("Z")
    restored = snap(game)
    assert restored == before, key
    assert restored.state.search_key() == before.state.search_key()
    assert restored.state.turns == before.state.turns
    player.press(key)
    assert snap(game) == after, key  # replaying the input gives the same result


def free_play(player, number):
    player.game.open_level(number)
    player.press("F")
    return player.game


def test_history_is_bounded_and_drops_the_oldest():
    state = initial_state(load(resource_path("levels", "chamber_01.json")))
    history = History(limit=3)
    for turn in range(5):
        history.push(Snapshot(replace(state, turns=turn), frozenset(), False, None))
    assert len(history) == 3
    assert [history.undo().state.turns for _ in range(3)] == [4, 3, 2]
    assert history.undo() is None


def test_history_skips_a_duplicate_of_the_top_entry():
    state = initial_state(load(resource_path("levels", "chamber_01.json")))
    history = History()
    entry = Snapshot(state, frozenset(), False, None)
    history.push(entry)
    history.push(entry)
    assert len(history) == 1


def test_undo_power_choices_record_save_launch_retry_and_restart(player):
    game = free_play(player, 3)
    undoes(player, "E")  # opening the console
    undoes(player, "SPACE")  # staging a circuit
    undoes(player, "RETURN")  # applying power
    undoes(player, "RETURN")  # record
    undoes(player, "RIGHT")  # recorded move
    undoes(player, "SPACE")  # recorded wait
    undoes(player, "RETURN")  # save recording
    undoes(player, "RETURN")  # launch
    undoes(player, "RIGHT")  # replay move
    undoes(player, "R")  # retry from launch
    undoes(player, "C")  # restart the chamber
    assert len(game.history) > 0


def test_undo_wait_in_replay_and_hidden_launch_alias(player):
    game = free_play(player, 3)
    for key in ("E", "SPACE", "RETURN", "RETURN", "RETURN"):
        player.press(key)
    undoes(player, "Q")  # the old launch key still launches, and still undoes
    assert game.state.phase.value == "replay"


def test_undo_free_hub_move(player, monkeypatch):
    game = free_play(player, 3)
    chamber = game.state.chamber
    wide = replace(chamber, hub=chamber.hub | {Position(12, 6)})
    game.state = initial_state(wide)
    undoes(player, "RIGHT")
    assert game.state.player == Position(12, 6)


def test_rejected_inputs_push_nothing(player):
    game = free_play(player, 2)
    depth, before = len(game.history), snap(game)
    for key in ("RIGHT", "SPACE", "R", "Z"):
        player.press(key)  # leaves the hub, no turn yet, no launch, no history
        assert len(game.history) == depth and snap(game) == before
    # An over-budget apply is refused and leaves state and history alone.
    player.press("E")
    for _ in game.state.chamber.circuits:
        player.press("SPACE")
        player.press("DOWN")
    assert game.pending == frozenset(c.id for c in game.state.chamber.circuits)
    depth, staged = len(game.history), snap(game)
    player.press("RETURN")
    assert snap(game) == staged and len(game.history) == depth
    assert game.attempt.unsafe_power_choices == 1


def test_undo_with_empty_history_is_a_disabled_action_with_a_reason(player):
    game = free_play(player, 1)
    assert len(game.history) == 0
    undo = controls.find(game.actions(), "undo")
    assert not undo.enabled and undo.reason
    before = snap(game)
    player.press("Z")
    assert snap(game) == before
    assert game.attempt.disabled_presses == {"undo": 1}
    assert game.message == undo.reason.upper() and game.attempt.undos == 0


def test_undo_never_calls_the_engine(player, monkeypatch):
    game = free_play(player, 3)
    for key in ("E", "SPACE", "RETURN", "RETURN", "RIGHT"):
        player.press(key)

    def boom(*args, **kwargs):
        raise AssertionError("undo must only restore stored states")

    for name in ("act", "enter", "launch", "retry", "clear"):
        monkeypatch.setattr(app.recording, name, boom)
    for _ in range(5):
        player.press("Z")
    assert game.state == initial_state(game.state.chamber)
    assert game.attempt.undos == 5


def test_backspace_also_undoes(player):
    game = free_play(player, 3)
    before = snap(game)
    player.press("E")
    player.press("BACKSPACE")
    assert snap(game) == before


def test_undo_walks_back_through_the_whole_session(player):
    game = free_play(player, 3)
    states = [snap(game)]
    for key in ("E", "SPACE", "RETURN", "RETURN", "RIGHT", "SPACE", "RETURN", "RETURN"):
        player.press(key)
        states.append(snap(game))
    for expected in reversed(states[:-1]):
        if snap(game) == expected:
            continue
        player.press("Z")
        assert snap(game) == expected
    assert len(game.history) == 0


def fail_in_replay(player):
    game = free_play(player, 2)
    for key in ("RETURN", "RETURN", "RETURN"):  # record, save, launch
        player.press(key)
    before = snap(game)
    player.press("RIGHT")  # steps into the dark path
    return game, before


def test_undo_across_a_failure_returns_the_pre_failure_state(player):
    game, before = fail_in_replay(player)
    assert game.failure is not None and game.failure.kind == "replay"
    assert snap(game) == before  # the card shows the view before the restore
    player.press("Z")
    assert game.failure is None and snap(game) == before
    assert game.attempt.failure_choices == {"undo": 1}


def test_retry_after_failure_then_undo_still_reaches_pre_failure_state(player):
    game, before = fail_in_replay(player)
    restored = game.failure.restored
    player.press("R")
    assert game.failure is None and game.state == restored
    assert game.attempt.resets == 1  # one failure, one reset
    assert game.attempt.failure_choices == {"retry": 1}
    player.press("Z")
    assert snap(game) == before


@pytest.mark.parametrize("key", ["RETURN", "SPACE", "UP"])
def test_any_other_key_takes_the_default_retry(player, key):
    game, _ = fail_in_replay(player)
    restored = game.failure.restored
    player.press(key)
    assert game.failure is None and game.state == restored
    assert game.attempt.resets == 1
