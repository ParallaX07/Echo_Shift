"""Stage the playable app beside its read-only resources."""

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
    (DEST / "assets").mkdir(parents=True)
    for name in ("atlas.png", "atlas.json", "palette.json"):
        shutil.copy2(ROOT / "assets" / name, DEST / "assets" / name)
    shutil.copytree(ROOT / "assets/fonts", DEST / "assets/fonts", dirs_exist_ok=True)
    audio = ROOT / "assets/audio"
    if audio.is_dir():
        shutil.copytree(audio, DEST / "assets/audio", dirs_exist_ok=True)


if __name__ == "__main__":
    main()
