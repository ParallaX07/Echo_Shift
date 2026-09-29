from dataclasses import replace
from pathlib import Path

from echo_shift.engine.loader import load
from echo_shift.engine.model import Pad, Phase, Position, initial_state
from echo_shift.engine.recording import act, clear, enter, launch, retry
from echo_shift.engine.turn import (
    Accepted,
    InteractAtConsole,
    Move,
    Rejected,
    Wait,
    refresh_devices,
    step,
)


def _recorded():
    chamber = load(Path(__file__).parents[2] / "levels/fixtures/example_60.json")
    state = act(
        initial_state(chamber), InteractAtConsole(frozenset({"lab-lights"}))
    ).state
    assert state.turns == 0
    state = enter(state)
    state = act(state, Move(1, 0)).state
    state = act(state, Wait()).state
    return chamber, enter(state)


def test_free_hub_movement_and_record_commit():
    chamber = load(Path(__file__).parents[2] / "levels/fixtures/example_60.json")
    expanded_hub = replace(chamber, hub=frozenset({Position(1, 1), Position(2, 1)}))
    state = initial_state(expanded_hub)
    wandered = act(state, Move(1, 0))
    assert isinstance(wandered, Accepted)
    assert wandered.state.turns == state.turns
    recording = enter(wandered.state)
    assert recording.phase is Phase.RECORDING
    assert enter(recording).phase is Phase.COMMITTED
    committed_wander = act(enter(recording), Move(1, 0))
    assert isinstance(committed_wander, Accepted)
    assert committed_wander.state.turns == 0


def test_retry_restores_launch_snapshot_and_clear_discards_take():
    _, committed = _recorded()
    committed = act(committed, InteractAtConsole(frozenset({"elevator-power"}))).state
    launched = launch(committed)
    advanced = act(launched, Move(1, 0)).state
    assert retry(advanced) == launched
    reset = clear(advanced)
    assert reset.phase is Phase.PREPARE
    assert not reset.recording and reset.echo_position is None
    assert not reset.powered_circuits


def test_launch_is_independent_of_hub_wandering_after_commit():
    chamber, committed = _recorded()
    committed = replace(
        committed,
        chamber=replace(chamber, hub=frozenset({Position(1, 1), Position(2, 1)})),
    )
    committed = act(committed, InteractAtConsole(frozenset({"elevator-power"}))).state
    immediate = launch(committed)
    wandered = act(committed, Move(1, 0)).state
    assert launch(wandered) == immediate
    assert immediate.player == chamber.start
    assert immediate.echo_position == immediate.echo_start
    assert immediate.echo_index == 0


def test_echo_holds_final_tile_for_one_turn():
    _, committed = _recorded()
    committed = act(committed, InteractAtConsole(frozenset({"elevator-power"}))).state
    state = launch(committed)
    first = act(state, Move(1, 0))
    assert isinstance(first, Accepted)
    second = act(first.state, Move(1, 0))
    assert isinstance(second, Accepted)
    hold = act(second.state, Move(1, 0))
    assert isinstance(hold, Accepted)
    assert hold.state.echo_hold == 1
    assert hold.state.echo_position == Position(2, 1)


def test_timed_pad_refresh_keeps_gate_open_after_echo_expiry(chamber_factory):
    chamber = chamber_factory()
    chamber = replace(chamber, pads=(replace(chamber.pads[0], timer_length=2),))
    state = initial_state(chamber, frozenset({"lab-power"}))
    state = replace(
        state,
        phase=Phase.REPLAY,
        recording=(Wait(),),
        player=Position(1, 1),
        echo_position=Position(2, 1),
        echo_index=1,
        echo_hold=1,
        pad_timers=(("pad-a", 2),),
    )
    state = refresh_devices(state)
    result = step(state, Wait())
    assert isinstance(result, Accepted)
    assert result.state.echo_position is None
    assert result.state.pad_timers == (("pad-a", 1),)
    assert result.state.gates_open == frozenset({"gate-a"})


def test_blocked_echo_command_is_consumed(chamber_factory):
    chamber = chamber_factory()
    state = replace(
        initial_state(chamber),
        phase=Phase.REPLAY,
        recording=(Move(1, 0),),
        echo_position=Position(2, 1),
    )
    result = step(state, Wait())
    assert isinstance(result, Accepted)
    assert result.state.echo_position == Position(2, 1)
    assert result.state.echo_index == 1


def test_echo_expiry_closes_gate_before_movement(chamber_factory):
    chamber = chamber_factory()
    chamber = replace(chamber, pads=(Pad("pad-a", Position(1, 1)),))
    state = refresh_devices(
        replace(
            initial_state(chamber, frozenset({"lab-power"})),
            phase=Phase.REPLAY,
            recording=(Move(1, 0),),
            player=Position(2, 1),
            echo_position=Position(1, 1),
            echo_index=1,
            echo_hold=1,
        )
    )
    result = step(state, Move(1, 0))
    assert isinstance(result, Rejected)
    assert result.state is state
