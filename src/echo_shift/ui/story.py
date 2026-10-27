"""Pyxel-free log terminals: optional story props on hub tiles.

A chamber file may list `terminals`, each a hub tile and a few short lines.
The rules never see them: they are floor props that open a reading card.
"""

from dataclasses import dataclass
from typing import Any

from echo_shift.engine.loader import LevelError
from echo_shift.engine.model import Chamber, Position, State

MAX_LINES = 3
MAX_LINE_CHARS = 64
MIN_SPACING = 3  # tiles apart (taxicab), so no tile touches two terminals


@dataclass(frozen=True)
class Terminal:
    position: Position
    lines: tuple[str, ...]


def _terminal(item: Any) -> Terminal:
    if not isinstance(item, dict) or set(item) != {"position", "lines"}:
        raise LevelError("a terminal needs a position and lines")
    position, lines = item["position"], item["lines"]
    if (
        not isinstance(position, list)
        or len(position) != 2
        or any(not isinstance(part, int) or isinstance(part, bool) for part in position)
    ):
        raise LevelError("terminal position must be a [x, y] integer position")
    if (
        not isinstance(lines, list)
        or not 1 <= len(lines) <= MAX_LINES
        or any(not isinstance(line, str) or not line.strip() for line in lines)
        or any(len(line) > MAX_LINE_CHARS for line in lines)
    ):
        raise LevelError(
            f"terminal lines must be 1 to {MAX_LINES} short non-empty strings "
            f"(at most {MAX_LINE_CHARS} characters)"
        )
    return Terminal(Position(*position), tuple(lines))


def load_terminals(data: Any, chamber: Chamber) -> tuple[Terminal, ...]:
    """Validate the `terminals` entry of a chamber file against its chamber."""
    if data is None:
        return ()
    if not isinstance(data, list):
        raise LevelError("terminals must be a list")
    terminals = tuple(_terminal(item) for item in data)
    seen: list[Position] = []
    for terminal in terminals:
        at = terminal.position
        if at not in chamber.hub:
            raise LevelError(f"terminal {(at.x, at.y)} must be on a hub tile")
        if at in chamber.consoles or at == chamber.start:
            raise LevelError(
                f"terminal {(at.x, at.y)} cannot be on the console or door"
            )
        if any(abs(at.x - o.x) + abs(at.y - o.y) < MIN_SPACING for o in seen):
            raise LevelError(f"terminal {(at.x, at.y)} is too close to another")
        seen.append(at)
    return terminals


def in_reach(state: State, terminals: tuple[Terminal, ...]) -> Terminal | None:
    """The terminal the player can read: on or next to it, in the hub, console not underfoot."""
    player = state.player
    if player not in state.chamber.hub or player in state.chamber.consoles:
        return None
    return next(
        (
            terminal
            for terminal in terminals
            if abs(terminal.position.x - player.x) + abs(terminal.position.y - player.y)
            <= 1
        ),
        None,
    )
