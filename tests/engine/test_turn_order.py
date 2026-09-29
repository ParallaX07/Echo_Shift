from dataclasses import replace

from echo_shift.engine.model import Position, initial_state
from echo_shift.engine.turn import Accepted, Failed, InteractAtConsole, Move, step


def test_step_1_refreshes_passive_pad_and_gate_state(chamber_factory):
    state = initial_state(chamber_factory(), frozenset({"lab-power"}))
    stale = replace(state, player=Position(1, 1), pad_occupied=frozenset({"pad-a"}))
    # Waiting runs step 1 and refreshes a stale passive-pad state.
    from echo_shift.engine.turn import Wait

    result = step(stale, Wait())
    assert isinstance(result, Accepted)
    assert result.state.pad_occupied == frozenset()
    assert result.state.gates_open == frozenset()


def test_step_2_applies_power_before_movement(chamber_factory):
    state = initial_state(chamber_factory())
    console = InteractAtConsole(frozenset({"lab-power"}))
    result = step(state, console)
    assert isinstance(result, Accepted)
    assert result.state.powered_circuits == frozenset({"lab-power"})


def test_step_3_moves_player(chamber_factory):
    state = initial_state(chamber_factory(), frozenset({"lab-power"}))
    result = step(state, Move(1, 0))
    assert isinstance(result, Accepted)
    assert result.state.player == Position(2, 1)


def test_step_4_updates_pad_and_gate(chamber_factory):
    state = initial_state(chamber_factory(), frozenset({"lab-power"}))
    result = step(state, Move(1, 0))
    assert isinstance(result, Accepted)
    assert result.state.pad_occupied == frozenset({"pad-a"})
    assert result.state.gates_open == frozenset({"gate-a"})


def test_step_5_checks_safety_after_the_turn(chamber_factory):
    state = initial_state(chamber_factory())
    result = step(state, Move(1, 0))
    assert isinstance(result, Failed)
    assert result.state.turns == 1
    assert "unlit" in result.reason


def test_gate_state_is_recomputed_after_steps_1_2_and_4(chamber_factory):
    from echo_shift.engine.turn import Wait

    state = initial_state(chamber_factory(), frozenset({"lab-power"}))
    stale = replace(state, pad_occupied=frozenset({"pad-a"}))
    after_step_1 = step(stale, Wait())
    assert isinstance(after_step_1, Accepted)
    assert after_step_1.state.gates_open == frozenset()

    chamber = chamber_factory(console=Position(2, 1))
    at_pad = step(initial_state(chamber), Move(1, 0))
    assert isinstance(at_pad, Failed)
    turned_on = step(at_pad.state, InteractAtConsole(frozenset({"lab-power"})))
    assert isinstance(turned_on, Accepted)
    assert turned_on.state.gates_open == frozenset({"gate-a"})

    at_pad_powered = step(state, Move(1, 0))
    assert isinstance(at_pad_powered, Accepted)
    assert at_pad_powered.state.gates_open == frozenset({"gate-a"})
