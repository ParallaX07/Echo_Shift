"""Package a PyInstaller build as a Linux AppImage and a tar.gz."""

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging/linux"
PYXEL = Path(importlib.util.find_spec("pyxel").submodule_search_locations[0])


def copy_dist(dist: Path, dest: Path) -> None:
    shutil.copytree(dist, dest, symlinks=True)
    (dest / "app").rename(dest / "echo-shift")
    # Pyxel falls back to its own SDL2 when the system has none, but
    # PyInstaller does not collect that copy.
    shutil.copytree(PYXEL / "libs", dest / "_internal/pyxel/libs", dirs_exist_ok=True)


def build_appimage(args: argparse.Namespace, workdir: Path) -> None:
    app_dir = workdir / "AppDir"
    copy_dist(args.dist, app_dir / "usr/lib/echo-shift")
    shutil.copy2(PACKAGING / "AppRun", app_dir / "AppRun")
    shutil.copy2(PACKAGING / "echo-shift.desktop", app_dir)
    shutil.copy2(PACKAGING / "echo-shift.png", app_dir)
    shutil.copy2(PACKAGING / "echo-shift.png", app_dir / ".DirIcon")
    icons = app_dir / "usr/share/icons/hicolor/512x512/apps"
    icons.mkdir(parents=True)
    shutil.copy2(PACKAGING / "echo-shift.png", icons)

    target = args.out / f"Echo_Shift-{args.version}-x86_64.AppImage"
    command = [str(args.appimagetool), "--appimage-extract-and-run"]
    if args.update_info:
        command += ["-u", args.update_info]
    subprocess.run(
        [*command, str(app_dir), str(target)],
        check=True,
        cwd=args.out,
        env={**os.environ, "ARCH": "x86_64"},
    )
    if args.update_info and not target.with_name(target.name + ".zsync").exists():
        sys.exit("no .zsync was generated; is zsyncmake on PATH?")


def build_tarball(args: argparse.Namespace, workdir: Path) -> None:
    name = f"Echo_Shift-{args.version}"
    copy_dist(args.dist, workdir / name)
    with tarfile.open(args.out / f"{name}-linux-x86_64.tar.gz", "w:gz") as tar:
        tar.add(workdir / name, arcname=name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=Path("dist/app"))
    parser.add_argument("--version", required=True)
    parser.add_argument("--update-info")
    parser.add_argument("--appimagetool", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("release"))
    args = parser.parse_args()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    args.appimagetool = args.appimagetool.resolve()
    with tempfile.TemporaryDirectory() as tmp:
        build_appimage(args, Path(tmp) / "appimage")
        build_tarball(args, Path(tmp) / "tarball")


if __name__ == "__main__":
    main()
