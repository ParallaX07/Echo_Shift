"""Recording controls and retry snapshots for the deterministic turn engine."""

from dataclasses import dataclass, replace

from . import lighting, power
from .model import Phase, Position, State, initial_state
from .turn import (
    Accepted,
    Action,
    Failed,
    InteractAtConsole,
    Move,
    Rejected,
    StepResult,
    Wait,
    _destination,
    collect_cell,
    refresh_devices,
    step,
)


@dataclass(frozen=True)
class PlaybackSnapshot:
    powered_circuits: frozenset[str]
    recording: tuple[Action, ...]
    echo_start: Position
    turns: int


def enter(state: State) -> State:
    """Start a recording from the current hub tile or commit the current take."""
    if state.phase is Phase.PREPARE and state.player in state.chamber.hub:
        # The turn counter measures the current take plus its replay, so a take
        # that failed earlier does not inflate the count of the one that wins.
        return replace(
            state,
            phase=Phase.RECORDING,
            recording=(),
            echo_start=state.player,
            turns=0,
        )
    if state.phase is Phase.RECORDING:
        return _committed(state)
    return state


def _committed(state: State) -> State:
    return refresh_devices(
        replace(
            state,
            player=state.chamber.start,
            phase=Phase.COMMITTED,
            echo_position=None,
            echo_index=0,
            echo_hold=0,
            pad_timers=tuple((pad.id, 0) for pad in state.chamber.pads),
            retry_snapshot=None,
        )
    )


def launch(state: State) -> State:
    """Reset the chamber, create an unadvanced echo, then snapshot it."""
    if state.phase is not Phase.COMMITTED or state.player not in state.chamber.hub:
        return state
    if state.echo_start is None:
        return state
    reset = initial_state(state.chamber, state.powered_circuits, state.cells_taken)
    replay = refresh_devices(
        replace(
            reset,
            phase=Phase.REPLAY,
            recording=state.recording,
            echo_start=state.echo_start,
            echo_position=state.echo_start,
            pad_timers=tuple((pad.id, 0) for pad in state.chamber.pads),
            turns=state.turns,
        )
    )
    snapshot = PlaybackSnapshot(
        replay.powered_circuits, replay.recording, replay.echo_start, replay.turns
    )
    return replace(replay, retry_snapshot=snapshot)


def retry(state: State) -> State:
    """Restore the playback starting configuration while retaining the recording."""
    snapshot = state.retry_snapshot
    if not isinstance(snapshot, PlaybackSnapshot):
        return state
    reset = initial_state(state.chamber, snapshot.powered_circuits, state.cells_taken)
    return refresh_devices(
        replace(
            reset,
            phase=Phase.REPLAY,
            recording=snapshot.recording,
            echo_start=snapshot.echo_start,
            echo_position=snapshot.echo_start,
            turns=snapshot.turns,
            retry_snapshot=snapshot,
        )
    )


def clear(state: State) -> State:
    """Reset the chamber and discard power selection, recording and echo."""
    return initial_state(state.chamber)


def act(state: State, action: Action) -> StepResult:
    """Apply gameplay input, including free hub actions and recording capture."""
    if state.phase in {Phase.PREPARE, Phase.COMMITTED}:
        if isinstance(action, Move):
            if (action.dx, action.dy) not in {(0, -1), (1, 0), (0, 1), (-1, 0)}:
                return Rejected(state, "move must be one cardinal tile")
            # Free roam: any lit, open tile that is not a live conduit. The world
            # does not react, so only the player moves (and may pick up a cell).
            destination = _destination(state, state.player, action.dx, action.dy)
            if destination is None:
                return Rejected(state, "wall or closed gate blocks movement")
            if destination in lighting.live_conduit_tiles(state):
                return Rejected(state, "that conduit is live")
            if destination not in lighting.lit_tiles(state):
                return Rejected(state, "too dark to walk there")
            return Accepted(collect_cell(replace(state, player=destination)))
        if isinstance(action, InteractAtConsole):
            if (
                state.player not in state.chamber.hub
                or state.player not in state.chamber.consoles
            ):
                return Rejected(state, "free power changes require the hub console")
            configured = power.apply(
                state.chamber, action.powered_circuits, power.capacity_of(state)
            )
            if not configured.ok:
                return Rejected(
                    state, configured.error or "invalid power configuration"
                )
            return Accepted(
                refresh_devices(replace(state, powered_circuits=configured.circuits))
            )
        return Rejected(state, "no turn is available before launch")

    if state.phase not in {Phase.RECORDING, Phase.REPLAY}:
        return Rejected(state, "the chamber is not accepting actions")
    if (
        state.phase is Phase.RECORDING
        and len(state.recording) >= state.chamber.max_turns
    ):
        return Rejected(state, "recording is full; press Enter to commit")
    result = step(state, action)
    if isinstance(result, Rejected):
        return result
    updated = result.state
    if state.phase is Phase.RECORDING:
        if isinstance(action, (Move, Wait)):
            updated = replace(updated, recording=(*state.recording, action))
        if isinstance(result, Failed):
            updated = refresh_devices(
                replace(
                    updated,
                    player=updated.chamber.start,
                    phase=Phase.PREPARE,
                    recording=(),
                    echo_start=None,
                    echo_position=None,
                    echo_index=0,
                    echo_hold=0,
                    pad_timers=tuple((pad.id, 0) for pad in updated.chamber.pads),
                    retry_snapshot=None,
                )
            )
    elif isinstance(result, Failed):
        updated = retry(updated)
    elif isinstance(result, Accepted) and result.succeeded:
        updated = replace(updated, phase=Phase.RESULT)
    if updated is not result.state:
        return type(result)(
            updated,
            **(
                {"reason": result.reason}
                if isinstance(result, Failed)
                else {"succeeded": result.succeeded}
                if isinstance(result, Accepted)
                else {}
            ),
        )
    return result
