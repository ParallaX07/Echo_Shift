"""Bounded undo stack of engine states plus the UI context around them."""

from collections import deque
from dataclasses import dataclass

from echo_shift.engine.model import State

LIMIT = 10_000


@dataclass(frozen=True)
class Snapshot:
    state: State
    pending: frozenset[str]
    console: bool
    lesson_index: int | None


class History:
    """Earlier snapshots, oldest dropped first. Undo restores; it never steps."""

    def __init__(self, limit: int = LIMIT) -> None:
        self._items: deque[Snapshot] = deque(maxlen=limit)

    def __len__(self) -> int:
        return len(self._items)

    def push(self, snapshot: Snapshot) -> None:
        if not self._items or self._items[-1] != snapshot:
            self._items.append(snapshot)

    def undo(self) -> Snapshot | None:
        return self._items.pop() if self._items else None

    def clear(self) -> None:
        self._items.clear()
