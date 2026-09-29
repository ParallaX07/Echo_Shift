"""Resource and per-user data paths."""

import os
import sys
from pathlib import Path


def resource_path(*parts: str) -> Path:
    """Resolve a bundled resource from the directory containing ``main.py``."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "main.py").is_file():
            return parent.joinpath(*parts)
    raise RuntimeError("could not locate main.py above the Echo Shift package")


def user_data_dir() -> Path:
    """Create and return the platform's Echo Shift user-data directory."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
        path = base / "EchoShift"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
        path = base / "echo-shift"
    path.mkdir(parents=True, exist_ok=True)
    return path
