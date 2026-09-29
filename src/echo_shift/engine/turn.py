"""Canonical, immutable turn resolution."""

from dataclasses import dataclass, replace

from . import lighting, power
from .model import Device, Position, State, TileType


@dataclass(frozen=True)
class Move:
    dx: int
    dy: int


@dataclass(frozen=True)
class Wait:
    pass


@dataclass(frozen=True)
class InteractAtConsole:
    powered_circuits: frozenset[str]


Action = Move | Wait | InteractAtConsole


@dataclass(frozen=True)
class Accepted:
    state: State
    succeeded: bool = False


@dataclass(frozen=True)
class Rejected:
    state: State
    reason: str


@dataclass(frozen=True)
class Failed:
    state: State
    reason: str


StepResult = Accepted | Rejected | Failed


def _device_active(state: State, device: Device) -> bool:
    return (
        device.circuit_id in state.powered_circuits
        and device.pad_id in state.pad_occupied
    )


def refresh_devices(state: State) -> State:
    """Recompute passive pad occupancy and linked gate/elevator state."""
    pads = frozenset(
        pad.id for pad in state.chamber.pads if pad.position == state.player
    )
    occupied = replace(state, pad_occupied=pads)
    gates = frozenset(
        device.id
        for device in state.chamber.devices
        if device.kind is TileType.GATE and _device_active(occupied, device)
    )
    elevators = frozenset(
        device.id
        for device in state.chamber.devices
        if device.kind is TileType.ELEVATOR and _device_active(occupied, device)
    )
    return replace(
        state, pad_occupied=pads, gates_open=gates, elevators_running=elevators
    )


def _validate_action(state: State, action: Action) -> str | None:
    if isinstance(action, Move):
        if (action.dx, action.dy) not in {(0, -1), (1, 0), (0, 1), (-1, 0)}:
            return "move must be one cardinal tile"
        destination = Position(state.player.x + action.dx, state.player.y + action.dy)
        tile = state.chamber.tile_at(destination)
        if tile is TileType.WALL:
            return "wall blocks movement"
        if tile is TileType.GATE and not any(
            device.position == destination and device.id in state.gates_open
            for device in state.chamber.devices
        ):
            return "closed gate blocks movement"
    elif isinstance(action, InteractAtConsole):
        if state.player not in state.chamber.consoles:
            return "player is not at a console"
        result = power.apply(state.chamber, action.powered_circuits)
        if not result.ok:
            return result.error
    elif not isinstance(action, Wait):
        return "unknown action"
    return None


def step(state: State, action: Action) -> StepResult:
    """Resolve an action in the locked five-step order.

    Step 1: refresh passive pads/devices (no echoes exist in this phase).
    Step 2: apply a valid console power configuration.
    Step 3: move or wait using current gate state.
    Step 4: update passive pads and linked devices.
    Step 5: check safety and the powered elevator exit.
    """
    reason = _validate_action(state, action)
    if reason:
        return Rejected(state, reason)

    # 1. Remove expired echoes and refresh pad/device state.
    current = refresh_devices(state)

    # 2. Apply power; validation above guarantees over-budget settings are refused.
    if isinstance(action, InteractAtConsole):
        configured = power.apply(current.chamber, action.powered_circuits)
        current = refresh_devices(
            replace(current, powered_circuits=configured.circuits)
        )

    # 3. Move using the gate state after step 2, or consume a wait/console turn.
    if isinstance(action, Move):
        current = replace(
            current,
            player=Position(current.player.x + action.dx, current.player.y + action.dy),
        )

    # 4. Update pads and devices for the next turn.
    current = refresh_devices(replace(current, turns=current.turns + 1))

    # 5. Safety and exit checks occur only at the end of the turn.
    if not lighting.is_safe(current, current.player):
        return Failed(current, "player ended the turn on an unlit tile")
    succeeded = any(
        device.kind is TileType.ELEVATOR
        and device.position == current.player
        and device.id in current.elevators_running
        for device in current.chamber.devices
    )
    return Accepted(current, succeeded)
