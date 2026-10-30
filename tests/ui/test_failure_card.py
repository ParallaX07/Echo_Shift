"""A failure shows a card first; the engine's restore applies only on retry."""

from echo_shift.engine.model import Phase, initial_state
from echo_shift.ui import controls


def start(player, number=2):
    game = player.game
    game.open_level(number)
    player.press("F")
    return game


def replay_failure(player):
    game = start(player)
    for key in ("RETURN", "RETURN", "RETURN"):
        player.press(key)
    assert game.state.phase is Phase.REPLAY
    player.press("RIGHT")  # the unpowered path is dark
    return game


def recording_failure(player):
    game = start(player)
    player.press("RETURN")
    assert game.state.phase is Phase.RECORDING
    player.press("RIGHT")
    return game


def shown(player):
    return " | ".join(str(text) for text in player.drawn)


def test_replay_failure_keeps_the_view_and_waits_for_a_choice(player):
    game = replay_failure(player)
    before = game.state
    assert game.failure.kind == "replay" and game.failure.reason
    assert before.phase is Phase.REPLAY and before.player == before.chamber.start
    restored = game.failure.restored
    assert restored.phase is Phase.REPLAY and restored.echo_index == 0
    player.drawn.clear()
    game.draw()
    text = shown(player)
    assert "ATTEMPT FAILED" in text
    assert "Z | Undo last move" in text and "R | Retry from launch" in text
    assert "C | Restart chamber" in text and "ANY OTHER KEY: RETRY FROM LAUNCH" in text
    assert game.state is before  # nothing applied yet
    assert game.attempt.resets == 1


def test_failure_card_actions_come_from_the_action_model(player):
    game = replay_failure(player)
    actions = {a.id: a for a in game.actions()}
    assert set(actions) >= {"undo", "retry", "restart"}
    assert actions["retry"].enabled and actions["undo"].enabled
    assert (actions["undo"].key, actions["retry"].key, actions["restart"].key) == (
        "Z",
        "R",
        "C",
    )


def test_retry_applies_the_restored_state_and_counts_one_reset(player):
    game = replay_failure(player)
    restored = game.failure.restored
    player.press("R")
    assert game.failure is None and game.state == restored
    assert game.attempt.resets == 1
    assert game.attempt.failure_choices == {"retry": 1}


def test_restart_clears_the_chamber(player):
    game = replay_failure(player)
    player.press("C")
    assert game.failure is None
    assert game.state == initial_state(game.state.chamber)
    assert game.attempt.failure_choices == {"restart": 1}
    player.press("Z")  # the failed run is still one undo away
    assert game.state.phase is Phase.REPLAY


def test_undo_returns_to_the_move_before_the_failure(player):
    game = replay_failure(player)
    before = game.state
    player.press("Z")
    assert game.failure is None and game.state == before
    assert game.attempt.failure_choices == {"undo": 1}
    assert game.attempt.undos == 1


def test_recording_failure_has_no_retry_but_a_default_path(player):
    game = recording_failure(player)
    assert game.failure.kind == "recording"
    retry = controls.find(game.actions(), "retry")
    assert not retry.enabled and retry.reason
    player.drawn.clear()
    game.draw()
    assert retry.reason in shown(player) or "R Retry from launch" in shown(player)
    restored = game.failure.restored
    assert restored.phase is Phase.PREPARE and not restored.recording
    player.press("SPACE")
    assert game.state == restored and game.failure is None
    assert game.attempt.resets == 1


def test_pressing_the_disabled_retry_key_on_a_recording_failure_is_counted(player):
    game = recording_failure(player)
    player.press("R")
    assert game.failure is None and game.state.phase is Phase.PREPARE
    assert game.attempt.disabled_presses == {"retry": 1}
    assert game.attempt.resets == 1


def test_held_key_cannot_dismiss_the_card(player):
    game = start(player)
    for key in ("RETURN", "RETURN", "RETURN"):
        player.press(key)
    right = player.fake.KEY_RIGHT
    player.held.add(right)
    player.pressed.add(right)
    game.update()  # the move fails and the card opens while Right is held
    assert game.failure is not None
    restored = game.failure.restored
    for _ in range(6):  # key repeat while still held
        game.update()
    assert game.failure is not None
    player.held.clear()
    player.pressed.clear()
    game.update()
    assert game.failure is not None
    player.press("RIGHT")
    assert game.failure is None and game.state == restored


def test_a_held_key_that_dismissed_the_card_cannot_move_on_repeat(player):
    game = recording_failure(player)
    game.update()
    left = player.fake.KEY_RIGHT
    player.pressed.add(left)
    player.held.add(left)
    game.update()  # the held key closes the card
    assert game.failure is None and game.message == "TAKE DISCARDED"
    before = (game.state, len(game.history))
    for _ in range(6):  # key repeat while it is still down
        player.pressed.add(left)
        game.update()
    assert (game.state, len(game.history)) == before
    assert game.message == "TAKE DISCARDED"
    player.pressed.clear()
    player.held.clear()
    game.update()
    player.press("RIGHT")  # released, so the next press plays again
    assert game.message != "TAKE DISCARDED"
