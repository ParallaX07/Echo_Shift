"""Local, anonymous playtest records; one JSON line per chamber visit."""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from echo_shift.paths import user_data_dir


def log_path() -> Path:
    return user_data_dir() / "playtest.jsonl"


@dataclass
class Attempt:
    chamber: int
    path: Path = field(default_factory=log_path)
    started: float = field(default_factory=time.monotonic)
    id: str = field(default_factory=lambda: uuid4().hex)
    resets: int = 0
    hints: int = 0
    unsafe_power_choices: int = 0
    finished: bool = False
    mode: str = "free"
    undos: int = 0
    disabled_presses: dict[str, int] = field(default_factory=dict)
    failure_choices: dict[str, int] = field(default_factory=dict)
    previews: list[int] = field(default_factory=list)

    def record_disabled(self, action_id: str) -> None:
        self.disabled_presses[action_id] = self.disabled_presses.get(action_id, 0) + 1

    def record_failure_choice(self, choice: str) -> None:
        self.failure_choices[choice] = self.failure_choices.get(choice, 0) + 1

    def record_preview(self, turn: int) -> None:
        self.previews.append(turn)

    def finish(self, completed: bool) -> None:
        if self.finished:
            return
        duration = round(time.monotonic() - self.started, 2)
        record = {
            "attempt_id": self.id,
            "chamber": self.chamber,
            "mode": self.mode,
            "completed": completed,
            "completion_time_seconds": duration if completed else None,
            "duration_seconds": duration,
            "resets": self.resets,
            "hints": self.hints,
            "unsafe_power_choices": self.unsafe_power_choices,
            "undos": self.undos,
            "disabled_presses": self.disabled_presses,
            "failure_choices": self.failure_choices,
            "previews": self.previews,
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")
        self.finished = True
