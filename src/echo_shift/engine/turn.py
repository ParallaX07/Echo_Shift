"""Canonical, immutable turn resolution."""

from dataclasses import dataclass, replace

from . import lighting, power
from .model import Position, State, TileType


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


def _occupied_pads(state: State) -> frozenset[str]:
    bodies = {state.player}
    if state.echo_position is not None:
        bodies.add(state.echo_position)
    return frozenset(pad.id for pad in state.chamber.pads if pad.position in bodies)


def _refresh(state: State) -> State:
    occupied = _occupied_pads(state)
    timers = dict(state.pad_timers)
    active = frozenset(
        pad.id
        for pad in state.chamber.pads
        if pad.id in occupied or timers.get(pad.id, 0) > 0
    )
    gates = frozenset(
        device.id
        for device in state.chamber.devices
        if device.kind is TileType.GATE
        and device.circuit_id in state.powered_circuits
        and device.pad_id in active
    )
    elevators = frozenset(
        device.id
        for device in state.chamber.devices
        if device.kind is TileType.ELEVATOR
        and device.circuit_id in state.powered_circuits
        and device.pad_id in active
    )
    return replace(
        state,
        pad_occupied=occupied,
        pad_active=active,
        gates_open=gates,
        elevators_running=elevators,
    )


def refresh_devices(state: State) -> State:
    """Recompute pad occupancy and linked device state without advancing timers."""
    return _refresh(state)


def _destination(state: State, position: Position, dx: int, dy: int) -> Position | None:
    destination = Position(position.x + dx, position.y + dy)
    tile = state.chamber.tile_at(destination)
    if tile is TileType.WALL:
        return None
    if tile is TileType.GATE and not any(
        device.position == destination and device.id in state.gates_open
        for device in state.chamber.devices
    ):
        return None
    return destination


def _validate_action(state: State, action: Action) -> str | None:
    if isinstance(action, Move):
        if (action.dx, action.dy) not in {(0, -1), (1, 0), (0, 1), (-1, 0)}:
            return "move must be one cardinal tile"
        if _destination(state, state.player, action.dx, action.dy) is None:
            return "wall or closed gate blocks movement"
    elif isinstance(action, InteractAtConsole):
        if state.player not in state.chamber.consoles:
            return "player is not at a console"
        result = power.apply(state.chamber, action.powered_circuits)
        if not result.ok:
            return result.error
    elif not isinstance(action, Wait):
        return "unknown action"
    return None


def _timer_update(state: State) -> tuple[tuple[str, int], ...]:
    bodies = {state.player}
    if state.echo_position is not None:
        bodies.add(state.echo_position)
    timers = dict(state.pad_timers)
    for pad in state.chamber.pads:
        if pad.position in bodies:
            timers[pad.id] = pad.timer_length
        elif pad.timer_length:
            timers[pad.id] = max(0, timers.get(pad.id, 0) - 1)
        else:
            timers[pad.id] = 0
    return tuple(sorted(timers.items()))


def step(state: State, action: Action) -> StepResult:
    """Resolve one accepted move, wait or console interaction in the documented turn order."""
    # 1. Expire the echo before refreshing pads and linked devices.
    current = state
    if current.echo_position is not None and current.echo_hold >= 1:
        current = replace(current, echo_position=None, echo_index=0, echo_hold=0)
    current = _refresh(current)

    reason = _validate_action(current, action)
    if reason:
        return Rejected(state, reason)

    # 2. Power takes effect before movement.
    if isinstance(action, InteractAtConsole):
        configured = power.apply(current.chamber, action.powered_circuits)
        current = _refresh(replace(current, powered_circuits=configured.circuits))

    # 3. Move the player and consume one echo command. Blocked echo moves are consumed.
    if isinstance(action, Move):
        current = replace(
            current,
            player=Position(current.player.x + action.dx, current.player.y + action.dy),
        )
    commands = current.recording
    echo_advanced = current.echo_position is not None and current.echo_index < len(
        commands
    )
    if echo_advanced:
        command = commands[current.echo_index]
        echo = current.echo_position
        if isinstance(command, Move):
            echo = _destination(current, echo, command.dx, command.dy) or echo
        current = replace(
            current, echo_position=echo, echo_index=current.echo_index + 1
        )

    # 4. Refresh timed pads/devices for the next turn.
    hold = current.echo_hold
    if (
        current.echo_position is not None
        and current.echo_index == len(commands)
        and not echo_advanced
    ):
        hold = min(1, hold + 1)
    current = replace(
        current,
        turns=current.turns + 1,
        echo_hold=hold,
        pad_timers=_timer_update(current),
    )
    current = _refresh(current)

    # 5. Check player safety and exit conditions.
    if not lighting.is_safe(current, current.player):
        return Failed(current, "player ended the turn on an unlit tile")
    succeeded = any(
        device.kind is TileType.ELEVATOR
        and device.position == current.player
        and device.id in current.elevators_running
        for device in current.chamber.devices
    )
    return Accepted(current, succeeded)
