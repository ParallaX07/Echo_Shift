"""HUD and timeline can be checked without opening Pyxel."""

from echo_shift.engine.loader import load
from echo_shift.engine.model import Phase, initial_state
from echo_shift.engine.recording import act, clear, enter, launch, retry
from echo_shift.engine.turn import Accepted, InteractAtConsole, Move, Wait
from echo_shift.paths import resource_path
from echo_shift.ui.hud import model


def walk(state, dx, steps=4):
    """Free hub moves between the door and the console."""
    for _ in range(steps):
        state = act(state, Move(dx, 0)).state
    return state


def test_hud_power_safety_and_timeline():
    state = initial_state(load(resource_path("levels", "chamber_04.json")))
    assert (model(state).load, model(state).capacity, model(state).safe) == (
        0,
        60,
        True,
    )
    state = walk(state, -1)
    state = act(state, InteractAtConsole(frozenset({"lab-lights"}))).state
    state = enter(walk(state, 1))
    state = act(state, Move(1, 0)).state
    state = act(state, Wait()).state
    assert model(state).timeline[:3] == (
        ("move", False, "R"),
        ("wait", False, ""),
        ("empty", False, ""),
    )
    state = walk(enter(state), -1)
    state = act(state, InteractAtConsole(frozenset({"lift-power"}))).state
    state = launch(state)
    hud = model(state)
    assert state.phase is Phase.REPLAY
    assert hud.load == 50
    assert hud.circuits == (("lab-lights", False), ("lift-power", True))
    assert hud.timeline[:2] == (("move", True, "R"), ("wait", False, ""))
    state = act(state, Move(1, 0)).state
    assert model(state).timeline[:2] == (("move", False, "R"), ("wait", True, ""))


def test_chamber_four_solve_ten_retries_and_clear():
    chamber = load(resource_path("levels", "chamber_04.json"))
    state = walk(initial_state(chamber), -1)
    state = act(state, InteractAtConsole(frozenset({"lab-lights"}))).state
    state = enter(walk(state, 1))
    for move in (Move(1, 0), Move(1, 0), Move(0, -1), Wait()):
        state = act(state, move).state
    state = walk(enter(state), -1)
    state = act(state, InteractAtConsole(frozenset({"lift-power"}))).state
    state = launch(state)
    route = (Move(1, 0), Move(1, 0), Wait(), Move(1, 0), Move(1, 0))
    for _ in range(10):
        for step_number, move in enumerate(route):
            result = act(state, move)
            assert isinstance(result, Accepted)
            assert result.succeeded is (step_number == len(route) - 1)
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
