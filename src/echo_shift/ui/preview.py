"""Pyxel-free look-ahead: what the next turns do if the player simply waits.

The engine is deterministic, so everything here is computed by running the real
turn function on copies of the state. Nothing is stored back into the live
state, and nothing is shown that the player could not work out from the rules.
"""

from dataclasses import dataclass, replace

from echo_shift.engine import recording
from echo_shift.engine.model import Chamber, Phase, Position, State, TileType
from echo_shift.engine.turn import Accepted, Failed, Move, Wait, step

PREVIEW_PHASES = (Phase.COMMITTED, Phase.REPLAY)
TURN_PHASES = (Phase.RECORDING, Phase.REPLAY)


@dataclass(frozen=True)
class Frame:
    """The chamber after `turn` turns since launch, assuming the player waits."""

    turn: int
    player: Position
    echo: Position | None
    pads_active: frozenset[str]
    pads_occupied: frozenset[str]
    timers: tuple[tuple[str, int], ...]
    gates_open: frozenset[str]
    elevators_running: frozenset[str]

    def timer(self, pad_id: str) -> int:
        return dict(self.timers).get(pad_id, 0)

    @property
    def running(self) -> frozenset[str]:
        """Gates that are open plus elevators that are running."""
        return self.gates_open | self.elevators_running


def frame_of(state: State, turn: int) -> Frame:
    return Frame(
        turn,
        state.player,
        state.echo_position,
        state.pad_active,
        state.pad_occupied,
        state.pad_timers,
        state.gates_open,
        state.elevators_running,
    )


@dataclass(frozen=True)
class Projection:
    """Consecutive frames: the present one, then one per predicted turn."""

    frames: tuple[Frame, ...]
    last_present: int

    @property
    def base(self) -> int:
        return self.frames[0].turn

    @property
    def turns(self) -> tuple[int, ...]:
        """Turns that can be previewed: every one after the present."""
        return tuple(frame.turn for frame in self.frames[1:])

    def previewable(self, turn: int | None) -> bool:
        return turn is not None and self.base < turn <= self.frames[-1].turn

    def at(self, turn: int) -> Frame | None:
        return next((f for f in self.frames if f.turn == turn), None)


def elapsed(state: State) -> int:
    """Turns taken since the echo launched; 0 before the launch."""
    if state.phase is not Phase.REPLAY:
        return 0
    return state.turns - getattr(state.retry_snapshot, "turns", state.turns)


def launch_state(state: State) -> State | None:
    """The state a launch would produce, built on a copy; None when not committed."""
    if state.phase is Phase.REPLAY:
        return state
    if state.phase is not Phase.COMMITTED:
        return None
    started = recording.launch(replace(state, player=state.chamber.start))
    return started if started.phase is Phase.REPLAY else None


def last_present(state: State) -> int | None:
    """The last turn the echo is on the board: the turn after its final command."""
    if state.phase not in PREVIEW_PHASES:
        return None
    return len(state.recording) + 1


def project(state: State) -> Projection | None:
    """Per-turn predictions through the echo's removal, or None before a commit."""
    start = launch_state(state)
    if start is None:
        return None
    present = len(start.recording) + 1
    turn = elapsed(start)
    frames = [frame_of(start, turn)]
    current = start
    while turn <= present:
        result = step(current, Wait())
        if not isinstance(result, (Accepted, Failed)):
            break
        current = result.state
        turn += 1
        frames.append(frame_of(current, turn))
    return Projection(tuple(frames), present)


def expiry_text(state: State) -> str | None:
    """The strip's plain-words line about when the echo leaves."""
    present = last_present(state)
    if present is None:
        return None
    if state.phase is Phase.REPLAY and state.echo_position is None:
        return "ECHO HAS LEFT"
    return f"ECHO LEAVES AFTER TURN {present}"


def next_command(state: State) -> tuple[str, tuple[int, int]] | None:
    """What the echo does on the next turn: ("move", (dx, dy)) or ("wait", (0, 0))."""
    if state.phase is not Phase.REPLAY or state.echo_position is None:
        return None
    if state.echo_index >= len(state.recording):
        return None
    command = state.recording[state.echo_index]
    if isinstance(command, Move):
        return "move", (command.dx, command.dy)
    return ("wait", (0, 0)) if isinstance(command, Wait) else None


def echo_path(state: State) -> tuple[Position, ...]:
    """Tiles the recorded echo walks through, from where it is (or will start)."""
    if state.phase is Phase.REPLAY:
        if state.echo_position is None:
            return ()
        here, index = state.echo_position, state.echo_index
    elif state.phase is Phase.COMMITTED and state.echo_start is not None:
        here, index = state.echo_start, 0
    else:
        return ()
    path = [here]
    for command in state.recording[index:]:
        if isinstance(command, Move):
            ahead = Position(here.x + command.dx, here.y + command.dy)
            if state.chamber.tile_at(ahead) is not TileType.WALL:
                here = ahead
        path.append(here)
    return tuple(path)


@dataclass(frozen=True)
class Markers:
    """Facts about the very next turn that the room labels directly."""

    countdowns: tuple[tuple[str, int], ...]
    closing: frozenset[str]


def countdowns(
    chamber: Chamber,
    pad_timers: tuple[tuple[str, int], ...],
    occupied: frozenset[str],
) -> tuple[tuple[str, int], ...]:
    """Turns of activity left on each timed pad; an occupied pad is full."""
    timers = dict(pad_timers)
    found = []
    for pad in chamber.pads:
        left = pad.timer_length if pad.id in occupied else timers.get(pad.id, 0)
        if pad.timer_length and left > 0:
            found.append((pad.id, left))
    return tuple(found)


def markers(state: State) -> Markers:
    """Timed-pad countdowns now, and devices that stop if the player waits."""
    countdown = countdowns(state.chamber, state.pad_timers, state.pad_occupied)
    closing: frozenset[str] = frozenset()
    if state.phase in TURN_PHASES:
        result = step(state, Wait())
        if isinstance(result, (Accepted, Failed)):
            after = result.state
            closing = (state.gates_open | state.elevators_running) - (
                after.gates_open | after.elevators_running
            )
    return Markers(countdown, closing)


@dataclass
class Browser:
    """Which predicted turn is on show, and when a new preview opens."""

    chosen: int | None = None
    hover: int | None = None
    shown: int | None = None

    def turn(self, projection: Projection | None) -> int | None:
        """The turn on show: a hovered slot wins over a chosen one."""
        if projection is None:
            return None
        for turn in (self.hover, self.chosen):
            if projection.previewable(turn):
                return turn
        return None

    def step(self, projection: Projection | None, delta: int) -> int | None:
        """Move the chosen turn by `delta`; the first press starts at an end."""
        if projection is None or not projection.turns:
            return None
        turns = projection.turns
        if projection.previewable(self.chosen):
            self.chosen = min(turns[-1], max(turns[0], self.chosen + delta))
        else:
            self.chosen = turns[0] if delta > 0 else turns[-1]
        return self.chosen

    def release(self) -> None:
        """Any gameplay key goes back to the live view."""
        self.chosen = None

    def opened(self, turn: int | None) -> int | None:
        """`turn` when it is newly on show since the last call, else None."""
        fresh = turn if turn != self.shown else None
        self.shown = turn
        return fresh

    def slot_turn(self, state: State, index: int, projection: Projection | None):
        """The turn a timeline slot previews, or None for empty or past slots."""
        turn = index + 1
        if index < len(state.recording) and projection and projection.previewable(turn):
            return turn
        return None
