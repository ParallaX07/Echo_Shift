from dataclasses import replace

from echo_shift.engine import recording
from echo_shift.engine.model import Phase, Position, initial_state
from echo_shift.engine.turn import Accepted, Move, Rejected

RIGHT = Move(1, 0)
LAMP = frozenset({"lamp"})
LAMP_ARC = frozenset({"lamp", "arc"})


def test_free_roam_walks_onto_lit_zone_tiles(wing_chamber):
    state = initial_state(wing_chamber, LAMP)
    for tile in (Position(2, 1), Position(3, 1)):
        result = recording.act(state, RIGHT)
        assert isinstance(result, Accepted)
        state = result.state
        assert state.player == tile
    assert state.turns == 0
    assert state.recording == ()
    assert state.phase is Phase.PREPARE


def test_free_roam_also_works_once_committed(wing_chamber):
    state = recording.act(recording.enter(initial_state(wing_chamber, LAMP)), RIGHT)
    state = recording.enter(state.state)
    assert state.phase is Phase.COMMITTED
    result = recording.act(state, RIGHT)
    assert isinstance(result, Accepted)
    assert result.state.player == Position(2, 1)


def test_an_unlit_tile_is_refused_without_changing_anything(wing_chamber):
    state = initial_state(wing_chamber)
    result = recording.act(state, RIGHT)
    assert isinstance(result, Rejected)
    assert result.reason == "too dark to walk there"
    assert result.state is state


def test_the_dark_gap_after_the_wing_is_refused(wing_chamber):
    state = replace(initial_state(wing_chamber, LAMP), player=Position(3, 1))
    result = recording.act(state, RIGHT)
    assert isinstance(result, Rejected)
    assert result.reason == "too dark to walk there"


def test_a_live_conduit_is_refused(wing_chamber):
    state = replace(initial_state(wing_chamber, LAMP_ARC), player=Position(2, 1))
    result = recording.act(state, RIGHT)
    assert isinstance(result, Rejected)
    assert result.reason == "that conduit is live"
    assert result.state is state


def test_walls_and_closed_gates_are_refused(wing_chamber):
    hub = initial_state(wing_chamber, LAMP)
    wall = recording.act(hub, Move(0, -1))
    assert isinstance(wall, Rejected)
    assert wall.reason == "wall or closed gate blocks movement"
    at_pad = replace(hub, player=Position(5, 1))
    gate = recording.act(at_pad, RIGHT)
    assert isinstance(gate, Rejected)
    assert gate.reason == "wall or closed gate blocks movement"


def test_only_cardinal_steps_are_accepted(wing_chamber):
    result = recording.act(initial_state(wing_chamber, LAMP), Move(1, 1))
    assert isinstance(result, Rejected)
    assert result.reason == "move must be one cardinal tile"


def test_the_world_does_not_react_to_a_free_walk(wing_chamber):
    base = initial_state(wing_chamber, LAMP)
    on_gap = replace(base, player=Position(4, 1))
    result = recording.act(on_gap, RIGHT)
    assert isinstance(result, Accepted)
    state = result.state
    assert state.player == Position(5, 1)
    assert state.pad_occupied == frozenset()
    assert state.pad_active == frozenset()
    assert state.gates_open == frozenset()
    assert state.pad_timers == base.pad_timers
    assert state.turns == 0


def test_free_roam_never_takes_the_exit(wing_chamber):
    base = initial_state(wing_chamber, LAMP)
    at_gate = replace(base, player=Position(6, 1))
    result = recording.act(at_gate, RIGHT)
    assert isinstance(result, Accepted)
    assert result.state.player == wing_chamber.exit
    assert not result.succeeded
    assert result.state.phase is Phase.PREPARE
    assert result.state.elevators_running == frozenset()


def test_recording_and_launch_still_need_a_hub_tile(wing_chamber):
    away = recording.act(initial_state(wing_chamber, LAMP), RIGHT).state
    assert recording.enter(away) is away
    committed = replace(away, phase=Phase.COMMITTED, echo_start=Position(1, 1))
    assert recording.launch(committed) is committed


def test_power_changes_still_need_the_console(wing_chamber):
    from echo_shift.engine.turn import InteractAtConsole

    away = recording.act(initial_state(wing_chamber, LAMP), RIGHT).state
    result = recording.act(away, InteractAtConsole(frozenset()))
    assert isinstance(result, Rejected)
    assert "console" in result.reason
