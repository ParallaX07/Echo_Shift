"""Small local save for the highest unlocked chamber."""

import json
from pathlib import Path

from echo_shift.paths import user_data_dir


def load_unlocked(level_count: int) -> int:
    path = user_data_dir() / "progress.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))["unlocked"]
    except (OSError, ValueError, KeyError, TypeError):
        return 1
    if not isinstance(value, int) or isinstance(value, bool):
        return 1
    return max(1, min(value, level_count))


def save_unlocked(value: int, directory: Path | None = None) -> None:
    path = (directory or user_data_dir()) / "progress.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"unlocked": value}) + "\n", encoding="utf-8")
    temporary.replace(path)
