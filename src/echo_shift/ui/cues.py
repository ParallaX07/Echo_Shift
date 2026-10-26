"""Pyxel-free facts behind the in-world cues: safety, links and console previews."""

from dataclasses import dataclass, replace

from echo_shift.engine import lighting
from echo_shift.engine.model import Device, Phase, Position, State, TileType
from echo_shift.ui import camera

STEPS = ((0, -1), (1, 0), (0, 1), (-1, 0))


def unsafe_neighbours(state: State) -> tuple[Position, ...]:
    """Unlit tiles next to the player that a move could actually enter.

    The hub is always lit, so these are all outside it. Walls and closed gates
    cannot be entered and are left out.
    """
    lit = lighting.lit_tiles(state)
    found = []
    for dx, dy in STEPS:
        tile = Position(state.player.x + dx, state.player.y + dy)
        kind = state.chamber.tile_at(tile)
        if kind is TileType.WALL or tile in lit:
            continue
        closed = any(
            d.position == tile and d.id not in state.gates_open
            for d in state.chamber.devices
            if d.kind is TileType.GATE
        )
        if not closed:
            found.append(tile)
    return tuple(found)


def warns_unsafe(state: State) -> bool:
    """Whether moves spend turns here, so stepping into the dark would fail."""
    return state.phase in (Phase.RECORDING, Phase.REPLAY)


@dataclass(frozen=True)
class DeviceLink:
    """Why a gate or elevator is open or closed: its circuit and its pad."""

    device: Device
    pad_position: Position
    pad_label: str
    powered: bool
    pad_active: bool

    @property
    def running(self) -> bool:
        return self.powered and self.pad_active


def link_for(state: State, device: Device) -> DeviceLink:
    pads = list(state.chamber.pads)
    index = next(i for i, pad in enumerate(pads) if pad.id == device.pad_id)
    return DeviceLink(
        device,
        pads[index].position,
        chr(ord("A") + index),
        device.circuit_id in state.powered_circuits,
        device.pad_id in state.pad_active,
    )


def focused_links(state: State, hover: Position | None) -> tuple[DeviceLink, ...]:
    """Links for the device under the pointer and any device next to the player."""
    links = []
    for device in state.chamber.devices:
        near = (
            abs(device.position.x - state.player.x)
            + abs(device.position.y - state.player.y)
            <= 1
        )
        if near or device.position == hover:
            links.append(link_for(state, device))
    return tuple(links)


@dataclass(frozen=True)
class ConsolePreview:
    """What a pending power choice would change in the room."""

    dark: frozenset[Position]
    lit: frozenset[Position]
    losing: frozenset[str]
    gaining: frozenset[str]

    @property
    def changed(self) -> bool:
        return bool(self.dark or self.lit or self.losing or self.gaining)


def console_preview(state: State, pending: frozenset[str]) -> ConsolePreview:
    before = lighting.lit_tiles(state)
    after = lighting.lit_tiles(replace(state, powered_circuits=pending))
    losing = {
        d.id
        for d in state.chamber.devices
        if d.circuit_id in state.powered_circuits and d.circuit_id not in pending
    }
    gaining = {
        d.id
        for d in state.chamber.devices
        if d.circuit_id in pending and d.circuit_id not in state.powered_circuits
    }
    return ConsolePreview(
        before - after, after - before, frozenset(losing), frozenset(gaining)
    )


@dataclass(frozen=True)
class Marker:
    """An edge arrow for something outside the view: `kind`, spot and direction."""

    kind: str
    x: float
    y: float
    dx: float
    dy: float


def offscreen_targets(
    state: State, echo: tuple[float, float, object] | None = None
) -> tuple[tuple[str, tuple[float, float]], ...]:
    """Gates, pads, elevators and the echo as (kind, tile position)."""
    found = [("pad", (pad.position.x, pad.position.y)) for pad in state.chamber.pads]
    found += [
        (
            "gate" if device.kind is TileType.GATE else "elevator",
            (device.position.x, device.position.y),
        )
        for device in state.chamber.devices
    ]
    if echo is not None:
        found.append(("echo", (echo[0], echo[1])))
    return tuple(found)


def offscreen_markers(
    view: camera.View,
    rect: camera.Rect,
    targets: tuple[tuple[str, tuple[float, float]], ...],
    inset: int,
) -> tuple[Marker, ...]:
    """Arrows on the edge of `rect` for each target whose tile is out of sight.

    Nothing is returned while every target is in view.
    """
    cell, origin_x, origin_y = view
    markers = []
    for kind, (x, y) in targets:
        if camera.visible(view, rect, x, y):
            continue
        spot = (origin_x + (x + 0.5) * cell, origin_y + (y + 0.5) * cell)
        found = camera.edge_marker(rect, spot, inset)
        if found is not None:
            (at_x, at_y), (dx, dy) = found
            markers.append(Marker(kind, at_x, at_y, dx, dy))
    return tuple(markers)
