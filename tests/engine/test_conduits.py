from dataclasses import replace

from echo_shift.engine import lighting, recording
from echo_shift.engine.model import Phase, Position, initial_state
from echo_shift.engine.turn import Accepted, Failed, Move, Wait, step

RIGHT = Move(1, 0)
LAMP_ARC = frozenset({"lamp", "arc"})
CONDUIT = Position(3, 1)


def test_only_a_powered_circuit_makes_its_conduit_live(wing_chamber):
    off = initial_state(wing_chamber, frozenset({"lamp"}))
    on = initial_state(wing_chamber, LAMP_ARC)
    assert lighting.live_conduit_tiles(off) == frozenset()
    assert lighting.live_conduit_tiles(on) == {CONDUIT}
    assert lighting.is_safe(off, CONDUIT)
    assert not lighting.is_safe(on, CONDUIT)


def test_an_unpowered_conduit_is_ordinary_floor(wing_chamber):
    state = recording.enter(initial_state(wing_chamber, frozenset({"lamp"})))
    state = recording.act(state, RIGHT).state
    result = recording.act(state, RIGHT)
    assert isinstance(result, Accepted)
    assert result.state.player == CONDUIT


def test_an_unpowered_conduit_in_the_dark_is_still_dark(wing_chamber):
    state = replace(initial_state(wing_chamber), phase=Phase.REPLAY, player=CONDUIT)
    result = step(state, Wait())
    assert isinstance(result, Failed)
    assert result.reason == "player ended the turn on an unlit tile"


def test_ending_a_turn_on_a_live_conduit_fails_with_its_own_reason(wing_chamber):
    state = recording.enter(initial_state(wing_chamber, LAMP_ARC))
    state = recording.act(state, RIGHT).state
    result = recording.act(state, RIGHT)
    assert isinstance(result, Failed)
    assert result.reason == "player ended the turn on a live conduit"
    assert result.state.phase is Phase.PREPARE


def test_live_conduit_wins_over_darkness_on_the_same_tile(wing_chamber):
    state = replace(
        initial_state(wing_chamber, frozenset({"arc"})),
        phase=Phase.REPLAY,
        player=Position(2, 1),
    )
    result = step(state, RIGHT)
    assert isinstance(result, Failed)
    assert result.reason == "player ended the turn on a live conduit"


def test_the_echo_is_immune_to_live_conduits(wing_chamber):
    base = initial_state(wing_chamber, LAMP_ARC)
    replay = replace(
        base,
        phase=Phase.REPLAY,
        recording=(RIGHT, RIGHT),
        echo_start=base.player,
        echo_position=base.player,
    )
    first = step(replay, Wait())
    second = step(first.state, Wait())
    assert isinstance(second, Accepted)
    assert second.state.echo_position == CONDUIT
    assert second.state.player == base.player
