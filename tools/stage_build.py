"""Stage the representative Pyxel application."""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "build/app"


def main() -> None:
    shutil.rmtree(DEST, ignore_errors=True)
    (DEST / "echo_shift").mkdir(parents=True)
    shutil.copy2(ROOT / "main.py", DEST / "main.py")
    shutil.copytree(ROOT / "src/echo_shift", DEST / "echo_shift", dirs_exist_ok=True)
    shutil.copytree(ROOT / "levels", DEST / "levels", dirs_exist_ok=True)
    (DEST / "assets/spike").mkdir(parents=True)
    for name in ("atlas.png", "atlas.json"):
        shutil.copy2(ROOT / "assets/spike" / name, DEST / "assets/spike" / name)


if __name__ == "__main__":
    main()
