from dataclasses import replace

from echo_shift.engine.model import Position, initial_state


def test_search_key_excludes_absolute_turn_count(chamber_factory):
    state = initial_state(chamber_factory())
    assert replace(state, turns=900).search_key() == state.search_key()


def test_search_key_includes_position_power_pad_and_gate_state(chamber_factory):
    state = initial_state(chamber_factory())
    variants = (
        replace(state, player=Position(2, 1)),
        replace(state, powered_circuits=frozenset({"lab-power"})),
        replace(state, pad_occupied=frozenset({"pad-a"})),
        replace(state, gates_open=frozenset({"gate-a"})),
    )
    assert all(variant.search_key() != state.search_key() for variant in variants)
    assert hash(state.search_key())
    assert hash(state)


def test_search_key_includes_timed_pad_counter(chamber_factory):
    state = initial_state(chamber_factory())
    assert state.search_key() != replace(state, pad_timers=(("pad-a", 1),)).search_key()
