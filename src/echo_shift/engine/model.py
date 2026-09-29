"""Immutable data model for the headless rules engine."""

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, order=True)
class Position:
    x: int
    y: int


class TileType(str, Enum):
    FLOOR = "floor"
    WALL = "wall"
    HUB = "hub"
    PAD = "pad"
    GATE = "gate"
    ELEVATOR = "elevator"
    CONSOLE = "console"


@dataclass(frozen=True)
class Zone:
    id: str
    tiles: tuple[Position, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "tiles", tuple(self.tiles))


@dataclass(frozen=True)
class Circuit:
    id: str
    load: int
    zones: tuple[str, ...] = ()
    devices: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "zones", tuple(self.zones))
        object.__setattr__(self, "devices", tuple(self.devices))


@dataclass(frozen=True)
class Pad:
    id: str
    position: Position


@dataclass(frozen=True)
class Device:
    id: str
    kind: TileType
    position: Position
    circuit_id: str
    pad_id: str


@dataclass(frozen=True)
class Chamber:
    tiles: tuple[tuple[TileType, ...], ...]
    start: Position
    hub: frozenset[Position]
    consoles: frozenset[Position]
    capacity: int
    zones: tuple[Zone, ...] = ()
    circuits: tuple[Circuit, ...] = ()
    pads: tuple[Pad, ...] = ()
    devices: tuple[Device, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "tiles",
            tuple(tuple(TileType(tile) for tile in row) for row in self.tiles),
        )
        object.__setattr__(self, "hub", frozenset(self.hub))
        object.__setattr__(self, "consoles", frozenset(self.consoles))
        for name in ("zones", "circuits", "pads", "devices"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        if (
            not self.tiles
            or not self.tiles[0]
            or any(len(row) != len(self.tiles[0]) for row in self.tiles)
        ):
            raise ValueError("chamber tiles must be a non-empty rectangle")
        if self.capacity < 0:
            raise ValueError("generator capacity cannot be negative")
        for position in self.hub | self.consoles | {self.start}:
            if not self.contains(position):
                raise ValueError(f"position outside chamber: {position}")
        for name, values in (
            ("circuit", self.circuits),
            ("zone", self.zones),
            ("pad", self.pads),
            ("device", self.devices),
        ):
            if len({value.id for value in values}) != len(values):
                raise ValueError(f"duplicate {name} id")
        circuits = {circuit.id: circuit for circuit in self.circuits}
        zones = {zone.id: zone for zone in self.zones}
        pads = {pad.id: pad for pad in self.pads}
        devices = {device.id: device for device in self.devices}
        for circuit in circuits.values():
            if circuit.load < 0:
                raise ValueError(f"circuit {circuit.id} has a negative load")
            if set(circuit.zones) - zones.keys():
                raise ValueError(f"circuit {circuit.id} links an unknown zone")
            if set(circuit.devices) - devices.keys():
                raise ValueError(f"circuit {circuit.id} links an unknown device")
        for device in devices.values():
            if device.circuit_id not in circuits or device.pad_id not in pads:
                raise ValueError(
                    f"device {device.id} has a dangling circuit or pad link"
                )
        positions = (
            *(position for zone in zones.values() for position in zone.tiles),
            *(pad.position for pad in pads.values()),
            *(device.position for device in devices.values()),
        )
        if any(not self.contains(position) for position in positions):
            raise ValueError("zone, pad or device position outside chamber")

    @property
    def width(self) -> int:
        return len(self.tiles[0])

    @property
    def height(self) -> int:
        return len(self.tiles)

    def contains(self, position: Position) -> bool:
        return 0 <= position.x < self.width and 0 <= position.y < self.height

    def tile_at(self, position: Position) -> TileType:
        if not self.contains(position):
            return TileType.WALL
        return self.tiles[position.y][position.x]


@dataclass(frozen=True)
class State:
    chamber: Chamber
    player: Position
    powered_circuits: frozenset[str] = frozenset()
    pad_occupied: frozenset[str] = frozenset()
    gates_open: frozenset[str] = frozenset()
    elevators_running: frozenset[str] = frozenset()
    turns: int = 0

    def __post_init__(self) -> None:
        for name in (
            "powered_circuits",
            "pad_occupied",
            "gates_open",
            "elevators_running",
        ):
            object.__setattr__(self, name, frozenset(getattr(self, name)))

    def search_key(self) -> tuple[object, ...]:
        """Return all current gameplay state, excluding absolute turn count."""
        return (
            self.player,
            self.powered_circuits,
            self.pad_occupied,
            self.gates_open,
            self.elevators_running,
        )


def initial_state(
    chamber: Chamber, powered_circuits: frozenset[str] = frozenset()
) -> State:
    from .power import apply

    configured = apply(chamber, powered_circuits)
    if not configured.ok:
        raise ValueError(configured.error)
    state = State(chamber, chamber.start, configured.circuits)
    from .turn import refresh_devices

    return refresh_devices(state)
