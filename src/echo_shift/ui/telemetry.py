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

    def finish(self, completed: bool) -> None:
        if self.finished:
            return
        duration = round(time.monotonic() - self.started, 2)
        record = {
            "attempt_id": self.id,
            "chamber": self.chamber,
            "completed": completed,
            "completion_time_seconds": duration if completed else None,
            "duration_seconds": duration,
            "resets": self.resets,
            "hints": self.hints,
            "unsafe_power_choices": self.unsafe_power_choices,
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")
        self.finished = True
