from dataclasses import replace
from pathlib import Path

from echo_shift.engine.loader import load
from echo_shift.engine.model import Pad, Phase, Position, initial_state
from echo_shift.engine.recording import act, enter, launch
from echo_shift.engine.turn import (
    Accepted,
    InteractAtConsole,
    Move,
    Rejected,
    Wait,
    refresh_devices,
    step,
)


def _committed():
    chamber = load(Path(__file__).parents[2] / "levels/fixtures/example_60.json")
    state = act(
        initial_state(chamber), InteractAtConsole(frozenset({"lab-lights"}))
    ).state
    state = enter(state)
    state = act(state, Move(1, 0)).state
    state = act(state, Wait()).state
    state = enter(state)
    state = act(state, InteractAtConsole(frozenset({"elevator-power"}))).state
    return chamber, state


def test_echo_overlaps_player_and_can_stand_in_darkness():
    _, state = _committed()
    state = launch(state)
    result = act(state, Move(1, 0))
    assert isinstance(result, Accepted)
    assert result.state.player == result.state.echo_position == Position(2, 1)
    _, state = _committed()
    state = launch(state)
    dark = act(state, InteractAtConsole(frozenset()))
    assert isinstance(dark, Accepted)
    assert dark.state.player == Position(1, 1)
    assert dark.state.echo_position == Position(2, 1)


def test_echo_arrives_holds_for_n_plus_one_then_expires_at_n_plus_two():
    _, state = _committed()
    state = launch(state)
    turn_n = act(state, Move(1, 0)).state
    turn_n = act(turn_n, Move(1, 0)).state
    assert turn_n.echo_position == Position(2, 1)
    assert turn_n.echo_hold == 0
    hold_turn = act(turn_n, Move(1, 0)).state
    assert hold_turn.echo_position == Position(2, 1)
    assert hold_turn.echo_hold == 1
    expired = step(hold_turn, Wait())
    assert isinstance(expired, Accepted)
    assert expired.state.echo_position is None


def test_gate_closes_before_player_movement_when_echo_expires(chamber_factory):
    chamber = chamber_factory()
    chamber = replace(chamber, pads=(Pad("pad-a", Position(1, 1)),))
    state = initial_state(chamber, frozenset({"lab-power"}))
    replay = refresh_devices(
        replace(
            state,
            phase=Phase.REPLAY,
            recording=(Move(1, 0),),
            player=Position(2, 1),
            echo_position=Position(1, 1),
            echo_index=1,
            echo_hold=1,
        )
    )
    assert replay.gates_open == frozenset({"gate-a"})
    result = step(replay, Move(1, 0))
    assert isinstance(result, Rejected)
    assert result.state is replay


def test_rejected_power_change_does_not_advance_echo(chamber_factory):
    chamber = chamber_factory(capacity=1)
    state = replace(
        initial_state(chamber),
        phase=Phase.REPLAY,
        recording=(Move(1, 0),),
        echo_position=Position(1, 1),
    )
    result = step(state, InteractAtConsole(frozenset({"lab-power"})))
    assert isinstance(result, Rejected)
    assert result.state is state
    assert result.state.echo_index == 0


def test_blocked_echo_command_is_consumed_without_failing(chamber_factory):
    chamber = chamber_factory()
    state = replace(
        initial_state(chamber),
        phase=Phase.REPLAY,
        recording=(Move(1, 0),),
        echo_position=Position(2, 1),
        echo_index=0,
    )
    result = step(state, Wait())
    assert isinstance(result, Accepted)
    assert result.state.echo_position == Position(2, 1)
    assert result.state.echo_index == 1


def test_timed_pad_countdown_and_search_key(chamber_factory):
    chamber = chamber_factory()
    chamber = replace(chamber, pads=(replace(chamber.pads[0], timer_length=3),))
    state = replace(
        initial_state(chamber, frozenset({"lab-power"})),
        player=Position(1, 1),
        pad_timers=(("pad-a", 2),),
    )
    assert state.search_key() != replace(state, pad_timers=(("pad-a", 1),)).search_key()
    first = step(state, Wait())
    assert isinstance(first, Accepted)
    assert first.state.pad_timers == (("pad-a", 1),)
    second = step(first.state, Wait())
    assert isinstance(second, Accepted)
    assert second.state.pad_timers == (("pad-a", 0),)
    assert "pad-a" not in second.state.pad_active


def test_machine_needs_both_power_and_active_pad(chamber_factory):
    chamber = chamber_factory()
    powered_empty = refresh_devices(initial_state(chamber, frozenset({"lab-power"})))
    assert "gate-a" not in powered_empty.gates_open
    at_pad = step(powered_empty, Move(1, 0))
    assert isinstance(at_pad, Accepted)
    unpowered = refresh_devices(replace(at_pad.state, powered_circuits=frozenset()))
    assert "pad-a" in unpowered.pad_active
    assert "gate-a" not in unpowered.gates_open


def test_recording_limit_refuses_more_actions_until_commit():
    chamber = load(Path(__file__).parents[2] / "levels/fixtures/example_60.json")
    chamber = replace(chamber, max_turns=1)
    state = act(
        initial_state(chamber), InteractAtConsole(frozenset({"lab-lights"}))
    ).state
    state = enter(state)
    state = act(state, Move(1, 0)).state
    refused = act(state, Wait())
    assert isinstance(refused, Rejected)
    assert refused.state is state
    power_change = act(state, InteractAtConsole(frozenset({"elevator-power"})))
    assert isinstance(power_change, Rejected)
    assert power_change.state is state
    assert enter(state).phase is Phase.COMMITTED
