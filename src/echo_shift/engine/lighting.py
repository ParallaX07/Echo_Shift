"""Light and safety queries."""

from .model import Position, State


def lit_tiles(state: State) -> frozenset[Position]:
    zones = {zone.id: zone for zone in state.chamber.zones}
    lit = set(state.chamber.hub)
    for circuit in state.chamber.circuits:
        if circuit.id in state.powered_circuits:
            for zone_id in circuit.zones:
                lit.update(zones[zone_id].tiles)
    return frozenset(lit)


def is_safe(state: State, tile: Position) -> bool:
    return tile in lit_tiles(state)
