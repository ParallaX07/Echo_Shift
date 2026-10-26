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


IDEAS = ("movement", "power", "echo", "darkness", "timed_pads", "combined")


@dataclass(frozen=True)
class Goals:
    """Targets for a chamber: total turns and recorded commands of a best run."""

    turns: int
    recorded: int

    def __post_init__(self) -> None:
        if self.turns < 1 or self.recorded < 0:
            raise ValueError("goals need at least one turn and no negative recording")


class Phase(str, Enum):
    PREPARE = "prepare"
    RECORDING = "recording"
    COMMITTED = "committed"
    REPLAY = "replay"
    RESULT = "result"


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
    timer_length: int = 0


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
    exit: Position | None = None
    max_turns: int = 12
    idea: str | None = None
    goals: Goals | None = None

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
        if not 1 <= self.max_turns <= 12:
            raise ValueError("max_turns must be an integer from 1 to 12")
        if self.idea is not None and self.idea not in IDEAS:
            raise ValueError(f"unknown idea: {self.idea}")
        if self.goals is not None and self.goals.recorded > self.max_turns:
            raise ValueError("recorded goal exceeds max_turns")
        for position in (
            self.hub
            | self.consoles
            | {self.start}
            | ({self.exit} if self.exit else set())
        ):
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
            if device.id not in circuits[device.circuit_id].devices:
                raise ValueError(f"device {device.id} is not linked from its circuit")
        if any(pad.timer_length < 0 for pad in pads.values()):
            raise ValueError("pad timer length cannot be negative")
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
    pad_active: frozenset[str] = frozenset()
    gates_open: frozenset[str] = frozenset()
    elevators_running: frozenset[str] = frozenset()
    turns: int = 0
    phase: Phase = Phase.PREPARE
    recording: tuple[object, ...] = ()
    echo_start: Position | None = None
    echo_position: Position | None = None
    echo_index: int = 0
    echo_hold: int = 0
    pad_timers: tuple[tuple[str, int], ...] = ()
    retry_snapshot: object | None = None

    def __post_init__(self) -> None:
        for name in (
            "powered_circuits",
            "pad_occupied",
            "pad_active",
            "gates_open",
            "elevators_running",
        ):
            object.__setattr__(self, name, frozenset(getattr(self, name)))
        object.__setattr__(self, "phase", Phase(self.phase))
        object.__setattr__(self, "recording", tuple(self.recording))
        object.__setattr__(self, "pad_timers", tuple(sorted(self.pad_timers)))

    def search_key(self) -> tuple[object, ...]:
        """Return all current gameplay state, excluding absolute turn count."""
        snapshot = self.retry_snapshot
        snapshot_key = (
            (
                getattr(snapshot, "powered_circuits", None),
                getattr(snapshot, "recording", None),
                getattr(snapshot, "echo_start", None),
            )
            if snapshot is not None
            else None
        )
        return (
            self.player,
            self.powered_circuits,
            self.pad_occupied,
            self.pad_active,
            self.gates_open,
            self.elevators_running,
            self.phase,
            self.pad_timers,
            self.recording,
            self.echo_start,
            self.echo_position,
            self.echo_index,
            self.echo_hold,
            snapshot_key,
        )


def initial_state(
    chamber: Chamber, powered_circuits: frozenset[str] = frozenset()
) -> State:
    from .power import apply

    configured = apply(chamber, powered_circuits)
    if not configured.ok:
        raise ValueError(configured.error)
    state = State(
        chamber,
        chamber.start,
        configured.circuits,
        pad_timers=tuple((pad.id, 0) for pad in chamber.pads),
    )
    from .turn import refresh_devices

    return refresh_devices(state)
