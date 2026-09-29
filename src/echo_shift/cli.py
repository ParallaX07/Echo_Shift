"""Command-line entry point for the game."""

import logging
import runpy
import sys
from pathlib import Path
from types import TracebackType


def _log_uncaught_exception(
    exc_type: type[BaseException],
    exc_value: BaseException,
    traceback: TracebackType | None,
) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, traceback)
        return
    logging.getLogger("echo_shift").critical(
        "Uncaught exception", exc_info=(exc_type, exc_value, traceback)
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    sys.excepthook = _log_uncaught_exception
    logging.getLogger("echo_shift").info("Starting Echo Shift")
    runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "main.py"), run_name="__main__"
    )
