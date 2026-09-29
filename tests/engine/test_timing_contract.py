from dataclasses import replace

from echo_shift.engine.model import Circuit, Device, Position, TileType, initial_state
from echo_shift.engine.turn import (
    Accepted,
    InteractAtConsole,
    Move,
    Rejected,
    step,
)


def test_rejected_inputs_do_not_advance_or_mutate(chamber_factory):
    state = initial_state(chamber_factory())
    result = step(state, Move(0, -1))
    assert isinstance(result, Rejected)
    assert result.state is state
    assert result.state.turns == 0


def test_over_budget_configuration_is_rejected(chamber_factory):
    state = initial_state(chamber_factory(capacity=1))
    result = step(state, InteractAtConsole(frozenset({"lab-power"})))
    assert isinstance(result, Rejected)
    assert result.state is state


def test_gate_requires_power_and_an_active_passive_pad(chamber_factory):
    chamber = chamber_factory()
    state = initial_state(chamber, frozenset({"lab-power"}))
    assert state.player == Position(1, 1)
    assert not state.gates_open
    on_pad = step(state, Move(1, 0))
    assert isinstance(on_pad, Accepted)
    assert on_pad.state.gates_open == frozenset({"gate-a"})
    no_power = replace(on_pad.state, powered_circuits=frozenset())
    from echo_shift.engine.turn import refresh_devices

    assert not refresh_devices(no_power).gates_open


def test_recomputes_gate_after_step_1_2_and_4(chamber_factory):
    from echo_shift.engine.turn import Wait

    state = initial_state(chamber_factory(), frozenset({"lab-power"}))
    stale = replace(state, pad_occupied=frozenset({"pad-a"}))
    step_1 = step(stale, Wait())
    assert isinstance(step_1, Accepted)
    assert not step_1.state.gates_open

    chamber = chamber_factory(console=Position(2, 1))
    on_pad_off = step(initial_state(chamber), Move(1, 0))
    assert not isinstance(on_pad_off, Rejected)
    step_2 = step(on_pad_off.state, InteractAtConsole(frozenset({"lab-power"})))
    assert isinstance(step_2, Accepted)
    assert step_2.state.gates_open == frozenset({"gate-a"})

    step_4 = step(state, Move(1, 0))
    assert isinstance(step_4, Accepted)
    assert step_4.state.gates_open == frozenset({"gate-a"})


def test_power_change_affects_same_turn_safety_check(chamber_factory):
    chamber = chamber_factory(console=Position(2, 1), start=Position(2, 1))
    result = step(initial_state(chamber), InteractAtConsole(frozenset({"lab-power"})))
    assert isinstance(result, Accepted)
    assert result.state.player == Position(2, 1)
    assert result.state.turns == 1


def test_powered_elevator_and_passive_pad_control_success(chamber_factory):
    chamber = chamber_factory()
    elevator = Device("lift", TileType.ELEVATOR, Position(2, 1), "lab-power", "pad-a")
    tiles = [list(row) for row in chamber.tiles]
    tiles[1][2] = TileType.ELEVATOR
    chamber = replace(
        chamber,
        tiles=tuple(tuple(row) for row in tiles),
        circuits=(Circuit("lab-power", 2, ("lab",), ("lift",)),),
        devices=(elevator,),
    )
    state = initial_state(chamber, frozenset({"lab-power"}))
    assert isinstance(step(state, Move(1, 0)), Accepted)
    assert step(state, Move(1, 0)).succeeded
