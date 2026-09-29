from echo_shift.engine import lighting
from echo_shift.engine.model import Position, initial_state


def test_hub_is_lit_with_everything_off(chamber_factory):
    state = initial_state(chamber_factory())
    assert lighting.is_safe(state, Position(1, 1))
    assert not lighting.is_safe(state, Position(2, 1))


def test_zone_is_lit_iff_its_circuit_is_on(chamber_factory):
    chamber = chamber_factory()
    off = initial_state(chamber)
    on = initial_state(chamber, frozenset({"lab-power"}))
    assert not lighting.is_safe(off, Position(2, 1))
    assert lighting.is_safe(on, Position(2, 1))
