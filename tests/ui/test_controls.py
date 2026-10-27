"""The action model: one table drives labels, availability and input."""

import re
from dataclasses import replace

import pytest

from echo_shift.engine.loader import load
from echo_shift.engine.model import Phase, Position, initial_state
from echo_shift.engine.recording import enter, launch
from echo_shift.engine.turn import Wait
from echo_shift.paths import resource_path
from echo_shift.ui import controls


@pytest.fixture
def phases():
    state = initial_state(load(resource_path("levels", "chamber_03.json")))
    recording = enter(state)
    committed = enter(recording)
    return {
        "prepare": state,
        "recording": recording,
        "committed": committed,
        "replay": launch(committed),
    }


def echo(state, **kwargs):
    return controls.find(
        controls.available_actions(state, "game", None, **kwargs), "echo"
    )


def away(state):
    return replace(state, player=Position(13, 6))


def test_echo_key_label_follows_phase_and_position(phases):
    expected = {
        "prepare": ("Record", True),
        "recording": ("Save recording", True),
        "committed": ("Launch echo", True),
        "replay": ("Echo running", False),
    }
    for name, (label, enabled) in expected.items():
        action = echo(phases[name])
        assert (action.label, action.enabled, action.key) == (label, enabled, "Enter")
    assert phases["committed"].phase is Phase.COMMITTED
    for name in ("prepare", "committed"):
        action = echo(away(phases[name]))
        assert not action.enabled and action.reason
    assert echo(away(phases["committed"])).label == "Return to hub to launch"
    assert echo(away(phases["recording"])).label == "Save recording"
    assert echo(away(phases["replay"])).label == "Echo running"


def test_echo_verb_matches_what_the_key_does(phases):
    verbs = {name: controls.echo_verb(state) for name, state in phases.items()}
    assert verbs == {
        "prepare": "record",
        "recording": "save",
        "committed": "launch",
        "replay": None,
    }
    assert controls.echo_verb(away(phases["committed"])) is None


def contexts(phases):
    states = list(phases.values()) + [away(s) for s in phases.values()]
    for state in states:
        for scope in controls.SCOPES:
            screen = scope if scope in ("title", "levels") else "game"
            modal = None if screen != "game" or scope == "play" else scope
            for undoable in (False, True):
                for failure in ("", "replay", "recording"):
                    yield controls.available_actions(
                        state, screen, modal, undoable=undoable, failure=failure
                    )


def test_every_disabled_action_has_a_reason_and_enabled_ones_none(phases):
    seen_disabled = set()
    for actions in contexts(phases):
        for action in actions:
            assert action.label
            if action.enabled:
                assert action.reason == ""
            else:
                assert action.reason.strip()
                seen_disabled.add(action.id)
    assert {"wait", "console", "echo", "undo", "retry", "rerecord"} <= seen_disabled


def test_undo_is_disabled_with_a_reason_only_when_history_is_empty(phases):
    state = phases["prepare"]
    for scope in ("play", "console", "pause", "failure"):
        modal = None if scope == "play" else scope
        empty = controls.find(controls.available_actions(state, "game", modal), "undo")
        ready = controls.find(
            controls.available_actions(state, "game", modal, undoable=True), "undo"
        )
        assert not empty.enabled and empty.reason and ready.enabled


def test_retry_needs_a_launch_and_the_failure_card_knows_the_kind(phases):
    assert not controls.find(
        controls.available_actions(phases["committed"], "game", None), "retry"
    ).enabled
    assert controls.find(
        controls.available_actions(phases["replay"], "game", None), "retry"
    ).enabled
    for kind, enabled in (("replay", True), ("recording", False)):
        card = controls.available_actions(
            phases["replay"], "game", "failure", undoable=True, failure=kind
        )
        assert controls.find(card, "retry").enabled is enabled
        assert controls.find(card, "undo").enabled
        assert controls.find(card, "restart").enabled
    assert {a.id for a in card} >= {"undo", "retry", "restart"}


def test_wait_and_rerecord_availability(phases):
    for name, wait, rerecord in (
        ("prepare", False, False),
        ("recording", True, True),
        ("committed", False, True),
        ("replay", True, False),
    ):
        actions = controls.available_actions(phases[name], "game", None)
        assert controls.find(actions, "wait").enabled is wait
        assert controls.find(actions, "rerecord").enabled is rerecord


def test_a_full_recording_disables_moves_and_wait_with_the_save_key_in_the_reason(
    phases,
):
    state = phases["recording"]
    full = replace(state, recording=(Wait(),) * state.chamber.max_turns)
    actions = controls.available_actions(full, "game", None)
    for action_id in (*controls.MOVE_IDS, "wait"):
        action = controls.find(actions, action_id)
        assert not action.enabled
        assert action.reason == "Recording full; Enter saves it"
    assert controls.find(actions, "echo").enabled
    room = replace(state, recording=(Wait(),) * (state.chamber.max_turns - 1))
    for action in controls.available_actions(room, "game", None):
        if action.id in (*controls.MOVE_IDS, "wait"):
            assert action.enabled


def test_rerecord_explains_why_it_is_unavailable_in_each_phase(phases):
    def rerecord(name):
        actions = controls.available_actions(phases[name], "game", None)
        return controls.find(actions, "rerecord")

    assert rerecord("replay").reason == (
        "The echo is running; C clears the chamber for a new take"
    )
    assert rerecord("prepare").reason == "There is no recording to discard"


def test_every_action_id_is_in_the_binding_table_and_keys_exist(phases):
    shown = {a.id for actions in contexts(phases) for a in actions}
    assert shown <= set(controls.BINDINGS)
    assert all(i in controls.BINDINGS for ids in controls.SCOPES.values() for i in ids)
    keyless = {i for i in shown if not controls.key_names(i)}
    assert keyless == {
        "rerecord",
        "quit_title",
        "settings",
        "controls",
        "music_volume",
        "sfx_volume",
        "reduced_motion",
    }
    gameplay = {
        a.id for a in controls.available_actions(phases["prepare"], "game", None)
    }
    assert gameplay == set(controls.SCOPES["play"])


def test_no_key_is_bound_to_two_verbs_in_one_context():
    for scope, ids in controls.SCOPES.items():
        owners: dict[str, str] = {}
        for action_id in ids:
            for key in controls.key_names(action_id):
                assert owners.setdefault(key, action_id) == action_id, (scope, key)


def test_q_is_a_hidden_alias_of_the_echo_key_only(phases):
    assert controls.BINDINGS["echo"].hidden == ("KEY_Q",)
    holders = [i for i in controls.BINDINGS if "KEY_Q" in controls.key_names(i)]
    assert holders == ["echo"]
    shown = [a for actions in contexts(phases) for a in actions]
    assert all(a.key != "Q" for a in shown)
    for actions in contexts(phases):
        text = controls.legend(actions, tuple(a.id for a in actions))
        assert not re.search(r"\bQ\b", text)


def test_chamber_select_key_exists_only_in_the_pause_menu():
    holders = [s for s, ids in controls.SCOPES.items() if "levels" in ids]
    assert holders == ["pause"]
    for scope, ids in controls.SCOPES.items():
        if scope != "pause":
            assert all("KEY_L" not in controls.key_names(i) for i in ids)
    assert controls.BINDINGS["levels"].keys == ("KEY_L",)


def test_locked_bindings():
    keys = {i: set(controls.BINDINGS[i].keys) for i in controls.BINDINGS}
    assert keys["move_up"] == {"KEY_W", "KEY_UP"}
    assert keys["wait"] == {"KEY_SPACE"}
    assert keys["console"] == {"KEY_E"}
    assert keys["echo"] == {"KEY_RETURN", "KEY_F"}
    assert keys["undo"] == {"KEY_Z", "KEY_BACKSPACE"}
    assert keys["retry"] == {"KEY_R"} and keys["restart"] == {"KEY_C"}
    assert keys["pause"] == {"KEY_ESCAPE", "KEY_P"}
    assert keys["guide"] == {"KEY_T"} and keys["hint"] == {"KEY_H"}
    assert keys["mute"] == {"KEY_M"} and keys["fullscreen"] == {"KEY_F11"}
    assert keys["rerecord"] == set()


def test_legend_lists_only_enabled_actions_with_their_key_caps(phases):
    committed = phases["committed"]
    actions = controls.available_actions(committed, "game", None)
    assert controls.legend(actions, ("console", "echo")) == "Enter Launch echo"
    (console,) = committed.chamber.consoles
    actions = controls.available_actions(
        replace(committed, player=console), "game", None
    )
    assert controls.legend(actions, ("console", "echo")) == (
        "E Power console  Enter Launch echo"
    )
    assert controls.legend(actions, ("rerecord",)) == "Re-record"


def test_every_input_action_changes_something_in_the_running_app(player):
    game = player.game
    skip = {"mute", "fullscreen", "rerecord"}
    for action_id in controls.SCOPES["play"]:
        if action_id in skip:
            continue
        game.open_level(1)
        player.press("F")
        game.notice("")
        before = (
            game.snapshot(),
            game.message,
            game.modal,
            game.paused,
            dict(game.attempt.disabled_presses),
        )
        player.press(controls.BINDINGS[action_id].keys[-1].removeprefix("KEY_"))
        after = (
            game.snapshot(),
            game.message,
            game.modal,
            game.paused,
            dict(game.attempt.disabled_presses),
        )
        assert after != before, action_id


def test_placeholders_resolve_from_the_binding_table():
    assert controls.resolve("Press {key:echo}.") == "Press Enter."
    assert controls.resolve("{label:rerecord}") == "Re-record"
    assert controls.resolve("{key:move_right}") == "D or Right"
    assert controls.resolve("{key:move}") == "WASD or the arrow keys"
    assert controls.resolve("{key:nav_prev}/{key:nav_next}") == "Up/Down"
    assert controls.resolve("no placeholders") == "no placeholders"
    for bad in ("{key:teleport}", "{key:echo", "{echo}", "{label:}", "oops}"):
        with pytest.raises(ValueError):
            controls.resolve(bad)


def test_every_binding_id_can_be_named_in_text():
    for action_id in controls.BINDINGS:
        key, label = "{key:" + action_id + "}", "{label:" + action_id + "}"
        assert controls.resolve(key) == controls.key_text(action_id)
        assert controls.resolve(label)


def test_disclosure_only_lists_play_actions_and_never_hides_always_shown_ones():
    assert set(controls.shown_actions(1)) <= set(controls.SCOPES["play"])
    for level in range(1, 8):
        assert set(controls.ALWAYS_SHOWN) <= controls.shown_actions(level)
        assert set(controls.MOVE_IDS) <= controls.shown_actions(level)
        assert controls.shown_actions(level) <= controls.shown_actions(level + 1)
