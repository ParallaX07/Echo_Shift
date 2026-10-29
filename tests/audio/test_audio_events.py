"""Effects and music follow engine results and screens; no audio device is used."""

import json
import logging
from dataclasses import replace
from types import SimpleNamespace

import pytest

from echo_shift.engine import recording
from echo_shift.engine.loader import load
from echo_shift.engine.model import Phase, Position, initial_state
from echo_shift.engine.turn import Accepted, Failed, Move, Rejected, Wait
from echo_shift.paths import resource_path
from echo_shift.ui import audio, progress
from echo_shift.ui.audio import Audio, Cue, Refusal, sfx_for


@pytest.fixture
def base():
    return initial_state(load(resource_path("levels", "chamber_03.json")))


class FakePlayer:
    """Records what would reach the speakers."""

    def __init__(self):
        self.Sound = lambda: SimpleNamespace(mml=lambda code: None)
        self.channels = [SimpleNamespace(gain=0.125) for _ in range(4)]
        self.played, self.stopped, self.busy = [], [], True

    def play(self, channel, sound, loop=False, **kwargs):
        self.played.append((channel, sound, loop))

    def stop(self, channel=None):
        self.stopped.append(channel)

    def play_pos(self, channel):
        return (0, 0.0) if self.busy else None


def folder(tmp_path, sfx=None, music=None):
    if sfx is not None:
        (tmp_path / "sfx.json").write_text(json.dumps(sfx))
    if music is not None:
        (tmp_path / "music.json").write_text(json.dumps(music))
    return tmp_path


def make(tmp_path, music=None, sfx=None):
    player = FakePlayer()
    sfx = {"move": "C", "fail": "C"} if sfx is None else sfx
    return Audio(player, folder(tmp_path, sfx, music)), player


def track(loop=True):
    return {"mml": ["C", "E", "G"], "loop": loop}


# --- effect for each engine result and state change --------------------------


def test_failure_and_refusals(base):
    assert sfx_for(base, Failed(base, "dark"), base) == "fail"
    assert sfx_for(base, Rejected(base, "wall or closed gate blocks"), base) == "reject"
    assert sfx_for(base, Refusal("Nothing to launch yet"), base) == "reject"


def test_over_budget_comes_from_the_engine_and_the_console(base):
    over = Rejected(base, "power load 5 exceeds capacity 4")
    assert sfx_for(base, over, base) == "over_budget"
    assert (
        sfx_for(base, Refusal("OVER BUDGET - REMOVE A CIRCUIT"), base) == "over_budget"
    )


def test_phase_changes(base):
    def after(before, **changes):
        return sfx_for(before, Accepted(base), replace(before, **changes))

    recording_state = replace(base, phase=Phase.RECORDING)
    committed = replace(base, phase=Phase.COMMITTED)
    assert after(base, phase=Phase.RECORDING) == "record_start"
    assert after(recording_state, phase=Phase.COMMITTED) == "commit"
    assert after(committed, phase=Phase.REPLAY) == "launch"
    replay = replace(base, phase=Phase.REPLAY, echo_index=3)
    assert after(replay, echo_index=0) == "launch"  # a retry restarts the echo
    assert after(replay, phase=Phase.RESULT) == "clear"


def test_taking_an_energy_cell_chimes_above_the_move_sound(base):
    moved = replace(base, player=Position(2, 2), cells_taken=frozenset({"c1"}))
    assert sfx_for(base, Accepted(moved), moved) == "pickup"
    plain = replace(base, player=Position(2, 2))
    assert sfx_for(base, Accepted(plain), plain) == "move"
    # Putting a cell back (undo, restart) is not a pickup.
    assert sfx_for(moved, Accepted(base), base) == "move"
    # The refused move onto a dark tile still sounds as a refusal.
    assert sfx_for(base, Rejected(base, "too dark to walk there"), base) == "reject"


def test_echo_expiry_only_during_replay(base):
    echo = Position(1, 1)
    replay = replace(base, phase=Phase.REPLAY, echo_position=echo)
    gone = replace(replay, echo_position=None)
    assert sfx_for(replay, Accepted(gone), gone) == "echo_expire"
    committed = replace(base, phase=Phase.COMMITTED, echo_position=echo)
    assert sfx_for(committed, None, replace(committed, echo_position=None)) is None


@pytest.mark.parametrize(
    "field,expected_on,expected_off",
    [
        ("powered_circuits", "power_on", "power_off"),
        ("pad_active", "pad_on", "pad_off"),
        ("gates_open", "gate_open", "gate_close"),
        ("elevators_running", "elevator_start", None),
    ],
)
def test_device_changes(base, field, expected_on, expected_off):
    on = replace(base, **{field: frozenset({"x"})})
    assert sfx_for(base, None, on) == expected_on
    assert sfx_for(on, None, base) == expected_off


def test_moves_waits_and_recorded_steps(base):
    step = Position(base.player.x + 1, base.player.y)
    assert sfx_for(base, None, replace(base, player=step)) == "move"
    assert sfx_for(base, None, replace(base, turns=base.turns + 1)) == "wait"
    take = replace(base, phase=Phase.RECORDING)
    taken = replace(take, player=step, recording=(Move(1, 0),))
    assert sfx_for(take, None, taken) == "record_tick"
    assert sfx_for(base, None, base) is None


def test_priority_fail_then_clear_then_devices(base):
    busy = replace(base, gates_open=frozenset({"g"}), powered_circuits=frozenset({"p"}))
    assert sfx_for(base, Failed(busy, "dark"), busy) == "fail"
    assert sfx_for(base, None, busy) == "gate_open"  # gate beats power
    solved = replace(busy, phase=Phase.RESULT)
    assert sfx_for(base, Accepted(solved, True), solved) == "clear"


def test_override_cue_beats_the_state_difference(base):
    replay = replace(
        base, phase=Phase.REPLAY, echo_index=3, gates_open=frozenset({"g"})
    )
    back = replace(replay, echo_index=0, gates_open=frozenset())
    assert sfx_for(replay, None, back) == "launch"
    assert sfx_for(replay, Cue("undo"), back) == "undo"
    committed = replace(back, phase=Phase.COMMITTED)
    assert sfx_for(replay, Cue("undo"), committed) == "undo"
    assert sfx_for(base, Failed(base, "dark"), base) == "fail"
    assert sfx_for(base, Cue("undo"), replace(base, phase=Phase.RESULT)) == "undo"


def test_ui_cue_sounds_only_when_the_state_is_silent(base):
    assert sfx_for(base, "ui_select", base) == "ui_select"
    powered = replace(base, powered_circuits=frozenset({"p"}))
    assert sfx_for(base, "ui_select", powered) == "power_on"


def test_loading_another_chamber_makes_no_state_sound(base):
    other = initial_state(load(resource_path("levels", "chamber_02.json")))
    loud = replace(other, phase=Phase.REPLAY, gates_open=frozenset({"g"}))
    assert sfx_for(base, "ui_select", loud) == "ui_select"
    assert sfx_for(base, None, loud) is None


def test_real_engine_steps_map_to_effects(base):
    state = base
    state = replace(state, player=next(iter(state.chamber.hub)))
    started = recording.enter(state)
    assert sfx_for(state, None, started) == "record_start"
    result = recording.act(started, Wait())
    assert sfx_for(started, result, result.state) == "record_tick"
    committed = recording.enter(result.state)
    assert sfx_for(result.state, None, committed) == "commit"
    launched = recording.launch(replace(committed, player=state.player))
    assert sfx_for(committed, None, launched) == "launch"


# --- the player ---------------------------------------------------------------


def test_effects_play_on_channel_three_only(tmp_path, base):
    sound, player = make(tmp_path)
    moved = replace(base, player=Position(base.player.x + 1, base.player.y))
    assert sound.on_transition(base, None, moved) == "move"
    sound.on_transition(base, Failed(base, "dark"), base)
    assert [channel for channel, *_ in player.played] == [3, 3]
    assert player.played[0][1] is sound.sfx["move"]


def test_unknown_effect_is_silent(tmp_path, base):
    sound, player = make(tmp_path, sfx={"fail": "C"})
    sound.on_transition(base, Rejected(base, "wall"), base)
    sound.play_sfx(None)
    assert player.played == []


def test_music_uses_channels_zero_to_two_and_loops(tmp_path):
    sound, player = make(
        tmp_path, music={"title": track(), "clear_sting": track(False)}
    )
    sound.play_music("title")
    assert [(ch, loop) for ch, _, loop in player.played] == [
        (0, True),
        (1, True),
        (2, True),
    ]
    assert set(player.stopped) == {0, 1, 2}  # channel 3 effects are never stopped
    player.played.clear()
    sound.play_music("clear_sting")
    assert [loop for *_, loop in player.played] == [False] * 3


def test_missing_track_stops_music_without_error(tmp_path):
    sound, player = make(tmp_path, music={"title": track()})
    sound.play_music("title")
    player.played.clear()
    sound.play_music("final")
    sound.play_music(None)
    assert player.played == [] and sound.enabled and not sound.warned


def test_absent_data_files_run_silently(tmp_path, caplog):
    player = FakePlayer()
    sound = Audio(player, tmp_path)
    sound.play_music("title")
    sound.play_sfx("move")
    assert player.played == [] and not caplog.records


def test_absent_stand_ins(tmp_path):
    sound, player = make(tmp_path, music={"title": track(), "play_calm": track()})
    sound.play_music("clear_sting")  # no sting baked: the title theme stands in
    assert sound.current == "title" and len(player.played) == 3
    player.played.clear()
    sound.play_music("play_replay")  # no replay variant: keep the calm track
    assert sound.current == "play_calm" and len(player.played) == 3


def test_sting_is_followed_by_title_music(tmp_path):
    sound, player = make(
        tmp_path, music={"title": track(), "clear_sting": track(False)}
    )
    sound.sync_music("clear_sting")
    assert sound.current == "clear_sting"
    sound.sync_music("clear_sting")  # still playing
    assert sound.current == "clear_sting"
    player.busy = False
    sound.sync_music("clear_sting")
    assert sound.current == "title"
    played = len(player.played)
    sound.sync_music("clear_sting")  # the screen has not changed: no replay
    assert sound.current == "title" and len(player.played) == played


def test_sync_music_restarts_only_on_a_change(tmp_path):
    sound, player = make(tmp_path, music={"play_calm": track()})
    sound.sync_music("play_calm")
    sound.sync_music("play_calm")
    assert len(player.played) == 3


def test_volumes_and_mute_scale_the_channels(tmp_path):
    sound, player = make(tmp_path)
    sound.apply_settings(progress.Settings(music_volume=7, sfx_volume=0))
    gains = [channel.gain for channel in player.channels]
    assert gains[:3] == [audio.BASE_GAIN] * 3 and gains[3] == 0
    sound.apply_settings(progress.Settings(music_volume=0, sfx_volume=7))
    gains = [channel.gain for channel in player.channels]
    assert gains[:3] == [0] * 3 and gains[3] == audio.BASE_GAIN
    sound.apply_settings(progress.Settings(mute=True))
    assert [channel.gain for channel in player.channels] == [0] * 4
    sound.apply_settings(progress.Settings())
    assert [channel.gain for channel in player.channels] == [audio.BASE_GAIN] * 4


def test_a_failing_device_logs_once_and_goes_silent(tmp_path, base, caplog):
    sound, player = make(tmp_path)

    def broken(*args, **kwargs):
        raise RuntimeError("no device")

    player.play = broken
    with caplog.at_level(logging.WARNING):
        sound.on_transition(base, Failed(base, "dark"), base)
        sound.on_transition(base, Failed(base, "dark"), base)
        sound.play_music("title")
    assert not sound.enabled
    assert len([r for r in caplog.records if "audio unavailable" in r.message]) == 1


def test_a_bad_file_logs_once_and_the_rest_still_loads(tmp_path, caplog):
    (tmp_path / "music.json").write_text("{not json")
    (tmp_path / "sfx.json").write_text(json.dumps({"move": "C"}))
    with caplog.at_level(logging.WARNING):
        sound = Audio(FakePlayer(), tmp_path)
    assert sound.music == {} and "move" in sound.sfx and sound.enabled
    assert len([r for r in caplog.records if "audio unavailable" in r.message]) == 1


def test_a_bad_mml_string_skips_only_that_entry(tmp_path):
    player = FakePlayer()

    def sound():
        def mml(code):
            if code == "bad":
                raise ValueError(code)

        return SimpleNamespace(mml=mml)

    player.Sound = sound
    found = Audio(player, folder(tmp_path, {"move": "C", "fail": "bad"}))
    assert set(found.sfx) == {"move"}


# --- which music a screen calls for -------------------------------------------


@pytest.mark.parametrize(
    "mode,modal,phase,level,expected",
    [
        ("title", None, Phase.PREPARE, 1, "title"),
        ("levels", None, Phase.PREPARE, 1, "title"),
        ("game", None, Phase.PREPARE, 2, "play_calm"),
        ("game", "lesson_choice", Phase.PREPARE, 2, "play_calm"),
        ("game", None, Phase.RECORDING, 2, "play_calm"),
        ("game", None, Phase.COMMITTED, 2, "play_calm"),
        ("game", None, Phase.REPLAY, 2, "play_replay"),
        ("game", "result", Phase.RESULT, 2, "clear_sting"),
        ("game", "result", Phase.RESULT, 6, "final"),
    ],
)
def test_music_follows_screen_and_phase(mode, modal, phase, level, expected):
    assert audio.music_for(mode, modal, phase, level, 6) == expected
