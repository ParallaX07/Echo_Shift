"""The game drives audio from one place; input and rules never wait on it."""

from dataclasses import replace

from echo_shift.engine.model import Phase
from echo_shift.ui import app, audio, progress


def heard(player):
    """Effect ids played so far (channel 3 only), then forget them."""
    names = {id(sound): name for name, sound in player.game.audio.sfx.items()}
    ids = [names[id(sound)] for channel, sound, _ in player.played if channel == 3]
    player.played.clear()
    return ids


def start(player, number=2):
    player.game.open_level(number)
    player.press("F")
    heard(player)


def test_every_effect_is_loaded_from_the_bundled_data(player):
    assert {"move", "fail", "clear", "ui_select"} <= player.game.audio.sfx.keys()


def test_menus_make_select_and_hover_sounds(player):
    player.press("RETURN")  # title -> chamber list
    assert heard(player) == ["ui_select"]
    player.press("DOWN")
    assert heard(player) == ["ui_hover"]
    player.press("DOWN")
    assert heard(player) == ["ui_hover"]
    player.press("UP")
    player.press("UP")
    assert heard(player) == ["ui_hover", "ui_hover"]
    player.press("UP")  # already on the first chamber
    assert heard(player) == []
    player.press("RETURN")
    assert player.game.mode == "game" and "ui_select" in heard(player)


def test_recording_run_uses_one_effect_per_step(player):
    start(player)
    player.press("RETURN")
    assert heard(player) == ["record_start"]
    player.press("SPACE")
    assert heard(player) == ["record_tick"]
    player.press("RETURN")
    assert heard(player) == ["commit"]
    player.press("RETURN")
    assert player.game.state.phase is Phase.REPLAY
    assert heard(player) == ["launch"]


def test_failure_and_refusal_sounds(player):
    start(player)
    player.press("RETURN")
    heard(player)
    player.press("RIGHT")  # a dark tile ends the take
    assert player.game.failure is not None
    assert heard(player) == ["fail"]


def test_refused_input_rejects(player):
    start(player)
    player.press("R")  # nothing to retry before a launch
    assert heard(player) == ["reject"]


def test_free_power_is_heard_through_the_same_hook(player):
    start(player, 1)
    player.to_console()
    heard(player)
    player.press("E")
    assert heard(player) == ["ui_select"]  # the console opens
    player.press("SPACE")  # toggling a circuit applies at once in a free chamber
    assert heard(player) == ["power_on"]
    player.press("SPACE")
    assert heard(player) == ["power_off"]


def test_changing_the_chamber_is_not_a_state_sound(player):
    player.game.open_level(2)
    player.game.update()
    assert heard(player) == []


def test_settings_apply_to_the_channels_at_once(player):
    game = player.game
    game.progress.settings.music_volume = 0
    game.progress.settings.mute = False
    game.update()
    gains = [channel.gain for channel in player.fake.channels]
    assert gains[:3] == [0, 0, 0] and gains[3] == audio.BASE_GAIN
    player.press("M")
    assert game.muted
    assert [channel.gain for channel in player.fake.channels] == [0] * 4
    player.press("M")
    assert player.fake.channels[3].gain == audio.BASE_GAIN
    assert progress.load(6).settings.mute is False


def test_music_context_follows_screen_and_phase(player):
    game = player.game
    sound = game.audio
    calls = []
    sound.play_music = lambda track: calls.append(track)
    game.update()
    assert calls == ["title"]
    start(player)
    assert calls[-1] == "play_calm"
    player.press("RETURN")
    player.press("RETURN")
    player.press("RETURN")
    assert game.state.phase is Phase.REPLAY and calls[-1] == "play_replay"
    game.state = replace(game.state, phase=Phase.RESULT)
    game.update()
    assert calls[-1] == "clear_sting"
    game.level = 6
    game.update()
    assert calls[-1] == "final"
    game.show_levels()
    game.update()
    assert calls[-1] == "title"


def launched(player):
    """A recorded wait, committed and launched, with the echo at its start."""
    start(player)
    for key in ("RETURN", "SPACE", "RETURN", "RETURN"):
        player.press(key)
    assert player.game.state.phase is Phase.REPLAY
    heard(player)


def test_undo_in_replay_plays_only_the_undo_effect(player):
    launched(player)
    player.press("SPACE")  # the echo takes its first step
    assert player.game.state.echo_index == 1
    assert heard(player) not in ([], ["undo"])
    player.press("Z")
    assert player.game.state.echo_index == 0
    assert heard(player) == ["undo"]


def test_undo_straight_after_launch_plays_only_the_undo_effect(player):
    launched(player)
    player.press("Z")
    assert player.game.state.phase is Phase.COMMITTED
    assert heard(player) == ["undo"]


def test_undo_from_a_failure_card_still_sounds_as_undo(player):
    start(player)
    player.press("RETURN")
    player.press("RIGHT")
    assert player.game.failure is not None
    heard(player)
    player.press("Z")
    assert player.game.failure is None
    assert heard(player) == ["undo"]


def test_restart_chamber_plays_only_the_override_effect(player):
    launched(player)
    player.press("SPACE")
    heard(player)
    player.press("C")
    assert player.game.state.phase is Phase.PREPARE
    assert heard(player) == ["ui_select"]


def test_rerecord_plays_only_the_override_effect(player):
    start(player)
    player.press("RETURN")
    player.press("SPACE")
    heard(player)
    player.press("P")
    player.game.pause_index = app.PAUSE_ITEMS.index("rerecord")
    heard(player)
    player.press("RETURN")
    assert player.game.state.phase is Phase.PREPARE
    assert heard(player) == ["ui_select"]
