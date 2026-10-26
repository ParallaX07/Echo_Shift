"""Small local save: unlocked chambers, goals met and player settings."""

import contextlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from echo_shift.paths import user_data_dir

VERSION = 2
MAX_VOLUME = 7
GOAL_KEYS = ("turns", "recorded")


@dataclass
class Settings:
    music_volume: int = MAX_VOLUME
    sfx_volume: int = MAX_VOLUME
    mute: bool = False
    reduced_motion: bool = False
    crt: bool = False


@dataclass
class Progress:
    unlocked: int = 1
    goals: dict[str, dict[str, bool]] = field(default_factory=dict)
    settings: Settings = field(default_factory=Settings)
    version: int = VERSION


def _int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _goals(value: object) -> dict[str, dict[str, bool]]:
    goals: dict[str, dict[str, bool]] = {}
    if not isinstance(value, dict):
        return goals
    for chamber, entry in value.items():
        if not (
            isinstance(chamber, str)
            and chamber.isascii()
            and chamber.isdigit()
            and int(chamber) > 0
        ):
            continue
        if not isinstance(entry, dict):
            continue
        goals[chamber] = {key: entry.get(key) is True for key in GOAL_KEYS}
    return goals


def _settings(value: object) -> Settings:
    settings = Settings()
    if not isinstance(value, dict):
        return settings
    for name in ("music_volume", "sfx_volume"):
        found = value.get(name)
        if _int(found) and 0 <= found <= MAX_VOLUME:
            setattr(settings, name, found)
    for name in ("mute", "reduced_motion", "crt"):
        found = value.get(name)
        if isinstance(found, bool):
            setattr(settings, name, found)
    return settings


def load(level_count: int, directory: Path | None = None) -> Progress:
    """Read the save, falling back to defaults field by field."""
    path = (directory or user_data_dir()) / "progress.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Progress()
    if not isinstance(data, dict):
        return Progress()
    unlocked = data.get("unlocked")
    return Progress(
        unlocked=max(1, min(unlocked, level_count)) if _int(unlocked) else 1,
        goals=_goals(data.get("goals")),
        settings=_settings(data.get("settings")),
    )


def save(progress: Progress, directory: Path | None = None) -> None:
    path = (directory or user_data_dir()) / "progress.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {**asdict(progress), "version": VERSION}
    handle, name = tempfile.mkstemp(dir=path.parent, prefix="progress-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")
        os.replace(name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(name)
        raise


def cleared(progress: Progress, number: int) -> bool:
    """A chamber counts as cleared once it has a goals entry or the next is open."""
    return number < progress.unlocked or str(number) in progress.goals


def record_goals(
    progress: Progress, number: int, *, turns: bool, recorded: bool
) -> bool:
    """Note a clear and the goals it met; a goal, once met, is never removed.

    Returns True when the entry changed, so the caller knows to save. Goals never
    affect which chambers are unlocked.
    """
    old = progress.goals.get(str(number), {})
    new = {
        "turns": turns or old.get("turns", False),
        "recorded": recorded or old.get("recorded", False),
    }
    if old == new:
        return False
    progress.goals[str(number)] = new
    return True
