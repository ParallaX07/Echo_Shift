"""Light and safety queries."""

from .model import Position, State

UNLIT = "player ended the turn on an unlit tile"
LIVE = "player ended the turn on a live conduit"


def lit_tiles(state: State) -> frozenset[Position]:
    zones = {zone.id: zone for zone in state.chamber.zones}
    lit = set(state.chamber.hub)
    for circuit in state.chamber.circuits:
        if circuit.id in state.powered_circuits:
            for zone_id in circuit.zones:
                lit.update(zones[zone_id].tiles)
    return frozenset(lit)


def live_conduit_tiles(state: State) -> frozenset[Position]:
    """Tiles of every conduit whose circuit is powered."""
    return frozenset(
        tile
        for conduit in state.chamber.conduits
        if conduit.circuit_id in state.powered_circuits
        for tile in conduit.tiles
    )


def hazard(state: State, tile: Position) -> str | None:
    """Why the player may not end a turn on `tile`, or None when it is safe."""
    if tile in live_conduit_tiles(state):
        return LIVE
    if tile not in lit_tiles(state):
        return UNLIT
    return None


def is_safe(state: State, tile: Position) -> bool:
    return hazard(state, tile) is None
