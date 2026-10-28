from dataclasses import replace

import pytest

from echo_shift.engine import power, recording
from echo_shift.engine.model import Phase, Position, initial_state
from echo_shift.engine.turn import (
    Accepted,
    Failed,
    InteractAtConsole,
    Move,
    Rejected,
    Wait,
    step,
)

RIGHT = Move(1, 0)
LAMP = frozenset({"lamp"})
LAMP_AUX = frozenset({"lamp", "aux"})
HUB = Position(1, 1)
CELL = Position(2, 1)


def prepared(chamber, config=LAMP):
    return initial_state(chamber, config)


def take_in_prepare(chamber, config=LAMP):
    """Free-roam onto the cell and back to the hub."""
    state = recording.act(prepared(chamber, config), RIGHT).state
    return recording.act(state, Move(-1, 0)).state


def test_free_roam_picks_up_a_cell(wing_chamber):
    result = recording.act(prepared(wing_chamber), RIGHT)
    assert isinstance(result, Accepted)
    assert result.state.cells_taken == {"c1"}
    assert power.capacity_of(result.state) == 5


def test_recording_move_picks_up_a_cell_after_moving(wing_chamber):
    started = recording.enter(prepared(wing_chamber))
    result = recording.act(started, RIGHT)
    assert isinstance(result, Accepted)
    assert result.state.cells_taken == {"c1"}
    assert result.state.turns == 1
    assert result.state.recording == (RIGHT,)


def test_a_cell_is_taken_once(wing_chamber):
    state = take_in_prepare(wing_chamber)
    again = recording.act(recording.act(state, RIGHT).state, Move(-1, 0)).state
    assert again.cells_taken == {"c1"}
    assert power.capacity_of(again) == 5


def test_capacity_grows_so_an_over_budget_choice_becomes_valid(wing_chamber):
    state = prepared(wing_chamber)
    refused = recording.act(state, InteractAtConsole(LAMP_AUX))
    assert isinstance(refused, Rejected)
    assert "exceeds capacity 3" in refused.reason
    with pytest.raises(ValueError):
        initial_state(wing_chamber, LAMP_AUX)
    taken = take_in_prepare(wing_chamber)
    accepted = recording.act(taken, InteractAtConsole(LAMP_AUX))
    assert isinstance(accepted, Accepted)
    assert accepted.state.powered_circuits == LAMP_AUX
    assert initial_state(wing_chamber, LAMP_AUX, taken.cells_taken).phase is (
        Phase.PREPARE
    )


def test_console_turn_in_replay_uses_the_grown_capacity(wing_chamber):
    taken = initial_state(wing_chamber, LAMP, frozenset({"c1"}))
    replay = replace(taken, phase=Phase.REPLAY)
    assert isinstance(step(replay, InteractAtConsole(LAMP_AUX)), Accepted)
    base = replace(prepared(wing_chamber), phase=Phase.REPLAY)
    assert isinstance(step(base, InteractAtConsole(LAMP_AUX)), Rejected)


def test_the_echo_never_picks_up_a_cell(wing_chamber):
    state = recording.act(recording.enter(prepared(wing_chamber)), RIGHT).state
    state = recording.act(state, Wait()).state
    launched = recording.launch(recording.enter(state))
    launched = replace(launched, cells_taken=frozenset())
    assert launched.phase is Phase.REPLAY
    result = step(launched, Wait())
    assert isinstance(result, Accepted)
    assert result.state.echo_position == CELL
    assert result.state.cells_taken == frozenset()


def test_cells_survive_launch(wing_chamber):
    state = take_in_prepare(wing_chamber)
    state = recording.act(recording.enter(state), Wait()).state
    launched = recording.launch(recording.enter(state))
    assert launched.phase is Phase.REPLAY
    assert launched.cells_taken == {"c1"}
    assert launched.player == HUB


def test_cells_survive_launch_with_a_choice_that_needs_them(wing_chamber):
    state = take_in_prepare(wing_chamber)
    state = recording.act(state, InteractAtConsole(LAMP_AUX)).state
    state = recording.act(recording.enter(state), Wait()).state
    launched = recording.launch(recording.enter(state))
    assert launched.powered_circuits == LAMP_AUX
    assert recording.retry(launched).powered_circuits == LAMP_AUX


def test_cells_taken_during_replay_survive_retry(wing_chamber):
    state = recording.act(recording.enter(prepared(wing_chamber)), Wait()).state
    launched = recording.launch(recording.enter(state))
    assert launched.cells_taken == frozenset()
    walked = recording.act(launched, RIGHT).state
    assert walked.cells_taken == {"c1"}
    restored = recording.retry(walked)
    assert restored.cells_taken == {"c1"}
    assert restored.player == HUB
    assert restored.phase is Phase.REPLAY
    assert restored.turns == launched.turns


def test_cells_taken_before_a_replay_failure_are_kept(wing_chamber):
    state = recording.act(recording.enter(prepared(wing_chamber, frozenset())), Wait())
    launched = recording.launch(recording.enter(state.state))
    # The wing is dark: the player takes the cell, then fails on its unlit tile.
    result = recording.act(launched, RIGHT)
    assert isinstance(result, Failed)
    assert result.state.cells_taken == {"c1"}
    assert result.state.phase is Phase.REPLAY
    assert result.state.player == HUB
    assert result.state.retry_snapshot.turns == launched.turns


def test_cells_survive_a_recording_failure(wing_chamber):
    started = recording.enter(prepared(wing_chamber, frozenset()))
    result = recording.act(started, RIGHT)
    assert isinstance(result, Failed)
    assert result.state.phase is Phase.PREPARE
    assert result.state.cells_taken == {"c1"}
    assert result.state.recording == ()


def test_restart_puts_every_cell_back(wing_chamber):
    taken = take_in_prepare(wing_chamber)
    cleared = recording.clear(taken)
    assert cleared.cells_taken == frozenset()
    assert power.capacity_of(cleared) == 3
    assert isinstance(recording.act(cleared, InteractAtConsole(LAMP_AUX)), Rejected)


def test_search_key_tells_taken_cells_apart(wing_chamber):
    base = prepared(wing_chamber)
    taken = replace(base, cells_taken=frozenset({"c1"}))
    assert base.search_key() != taken.search_key()
    assert (
        taken.search_key() == replace(base, cells_taken=frozenset({"c1"})).search_key()
    )


def test_a_chamber_without_cells_keeps_its_capacity(chamber_factory):
    state = initial_state(chamber_factory(capacity=2))
    assert power.capacity_of(state) == 2
    assert state.cells_taken == frozenset()
