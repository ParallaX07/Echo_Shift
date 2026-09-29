"""Command-line entry point for the game."""

import runpy
from pathlib import Path


def main() -> None:
    runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "main.py"), run_name="__main__"
    )
