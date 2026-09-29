from echo_shift.engine.model import Position, initial_state
from echo_shift.engine.turn import Accepted, Move, Rejected, Wait, step


def test_wall_blocks_without_advancing(chamber_factory):
    state = initial_state(chamber_factory())
    result = step(state, Move(0, -1))
    assert isinstance(result, Rejected)
    assert result.state == state


def test_closed_gate_blocks_movement(chamber_factory):
    state = initial_state(chamber_factory())
    result = step(state, Move(1, 0))
    assert not isinstance(result, Rejected)
    result = step(result.state, Move(1, 0))
    assert isinstance(result, Rejected)
    assert result.state.player == Position(2, 1)


def test_wait_consumes_one_turn(chamber_factory):
    state = initial_state(chamber_factory())
    result = step(state, Wait())
    assert isinstance(result, Accepted)
    assert result.state.turns == 1
