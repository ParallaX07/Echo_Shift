"""HUD and timeline can be checked without opening Pyxel."""

from echo_shift.engine.loader import load
from echo_shift.engine.model import Phase, initial_state
from echo_shift.engine.recording import act, clear, enter, launch, retry
from echo_shift.engine.turn import Accepted, InteractAtConsole, Move, Wait
from echo_shift.paths import resource_path
from echo_shift.ui.hud import model


def test_hud_power_safety_and_timeline():
    state = initial_state(load(resource_path("levels", "chamber_proto.json")))
    assert (model(state).load, model(state).capacity, model(state).safe) == (
        0,
        60,
        True,
    )
    state = act(state, InteractAtConsole(frozenset({"lab-lights"}))).state
    state = enter(state)
    state = act(state, Move(1, 0)).state
    state = act(state, Wait()).state
    assert model(state).timeline[:3] == (
        ("move", False, "R"),
        ("wait", False, ""),
        ("empty", False, ""),
    )
    state = enter(state)
    state = act(state, InteractAtConsole(frozenset({"elevator-power"}))).state
    state = launch(state)
    hud = model(state)
    assert state.phase is Phase.REPLAY
    assert hud.load == 50
    assert hud.circuits == (("lab-lights", False), ("elevator-power", True))
    assert hud.timeline[:2] == (("move", True, "R"), ("wait", False, ""))
    state = act(state, Move(1, 0)).state
    assert model(state).timeline[:2] == (("move", False, "R"), ("wait", True, ""))


def test_prototype_solve_ten_retries_and_clear():
    chamber = load(resource_path("levels", "chamber_proto.json"))
    state = initial_state(chamber)
    state = act(state, InteractAtConsole(frozenset({"lab-lights"}))).state
    state = enter(state)
    state = act(state, Move(1, 0)).state
    state = act(state, Wait()).state
    state = enter(state)
    state = act(state, InteractAtConsole(frozenset({"elevator-power"}))).state
    state = launch(state)
    for _ in range(10):
        for step_number in range(4):
            result = act(state, Move(1, 0))
            assert isinstance(result, Accepted)
            assert result.succeeded is (step_number == 3)
            state = result.state
        state = retry(state)
        assert state.phase is Phase.REPLAY
        assert state.player == chamber.start
        assert state.echo_index == 0
        assert state.echo_position == state.echo_start
    cleared = clear(state)
    assert cleared.phase is Phase.PREPARE
    assert not cleared.recording
    assert not cleared.powered_circuits
    assert cleared.echo_position is None
