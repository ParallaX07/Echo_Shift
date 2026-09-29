"""Pure HUD data derived from engine state."""

from dataclasses import dataclass

from echo_shift.engine.lighting import is_safe
from echo_shift.engine.model import Phase, State
from echo_shift.engine.turn import Move, Wait


@dataclass(frozen=True)
class Hud:
    load: int
    capacity: int
    safe: bool
    circuits: tuple[tuple[str, bool], ...]
    timeline: tuple[tuple[str, bool, str], ...]


def model(state: State) -> Hud:
    load = sum(c.load for c in state.chamber.circuits if c.id in state.powered_circuits)
    slots = []
    for index in range(12):
        action = state.recording[index] if index < len(state.recording) else None
        kind = (
            "move"
            if isinstance(action, Move)
            else "wait"
            if isinstance(action, Wait)
            else "empty"
        )
        direction = (
            {(0, -1): "U", (1, 0): "R", (0, 1): "D", (-1, 0): "L"}[
                (action.dx, action.dy)
            ]
            if isinstance(action, Move)
            else ""
        )
        current = (
            state.phase is Phase.REPLAY
            and index == state.echo_index
            and action is not None
        )
        slots.append((kind, current, direction))
    return Hud(
        load,
        state.chamber.capacity,
        is_safe(state, state.player),
        tuple((c.id, c.id in state.powered_circuits) for c in state.chamber.circuits),
        tuple(slots),
    )
