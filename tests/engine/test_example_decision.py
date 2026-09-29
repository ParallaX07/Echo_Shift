from pathlib import Path

from echo_shift.engine.loader import load
from echo_shift.engine.model import Phase, initial_state
from echo_shift.engine.recording import act, enter, launch
from echo_shift.engine.turn import Accepted, InteractAtConsole, Move, Wait


def test_example_60_record_reconfigure_replay_and_capacity_decision():
    chamber = load(Path(__file__).parents[2] / "levels/fixtures/example_60.json")
    assert chamber.capacity == 60
    assert {circuit.id: circuit.load for circuit in chamber.circuits} == {
        "lab-lights": 30,
        "elevator-power": 50,
    }
    state = act(
        initial_state(chamber), InteractAtConsole(frozenset({"lab-lights"}))
    ).state
    state = enter(state)
    state = act(state, Move(1, 0)).state
    state = act(state, Wait()).state
    state = enter(state)
    assert state.phase is Phase.COMMITTED
    assert state.player == chamber.start
    assert len(state.recording) == 2
    state = act(state, InteractAtConsole(frozenset({"elevator-power"}))).state
    state = launch(state)
    assert state.phase is Phase.REPLAY
    for _ in range(4):
        result = act(state, Move(1, 0))
        assert isinstance(result, Accepted)
        state = result.state
    assert result.succeeded

    from echo_shift.engine.power import apply

    both = apply(chamber, frozenset({"lab-lights", "elevator-power"}))
    assert not both.ok
