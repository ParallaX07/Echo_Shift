"""Launch a built executable and check that the game starts."""

import argparse
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MARKER = "Echo Shift started"
LOG_DIRS = ("echo-shift", "EchoShift")


def read_log(data: Path) -> str | None:
    for name in LOG_DIRS:
        log = data / name / "startup.log"
        if log.is_file():
            return log.read_text(errors="replace")
    return None


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        proc.terminate()
    else:
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if sys.platform == "win32":
            proc.kill()
        else:
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--settle", type=float, default=5)
    args = parser.parse_args()
    executable = args.executable.resolve()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        work = Path(tmp, "cwd")
        data = Path(tmp, "data")
        work.mkdir()
        data.mkdir()
        output = Path(tmp, "output.txt")
        env = {**os.environ, "XDG_DATA_HOME": str(data), "APPDATA": str(data)}
        with output.open("wb") as sink:
            proc = subprocess.Popen(
                [str(executable)],
                cwd=work,
                env=env,
                stdout=sink,
                stderr=subprocess.STDOUT,
                start_new_session=sys.platform != "win32",
            )
            deadline = time.monotonic() + args.seconds
            started = False
            while time.monotonic() < deadline and proc.poll() is None:
                if MARKER in (read_log(data) or ""):
                    started = True
                    break
                time.sleep(0.25)
            if started:
                # The marker is written before resources load; keep watching.
                time.sleep(args.settle)
            exited = proc.poll()
            stop(proc)
        if started and exited is None:
            print(f"ok: {executable.name} started and kept running")
            return
        reason = (
            f"exited early with code {exited}"
            if exited is not None
            else f"no start-up marker within {args.seconds:g}s"
        )
        print(f"FAILED: {executable.name} {reason}")
        print("--- output ---")
        print(output.read_text(errors="replace"))
        print("--- startup.log ---")
        print(read_log(data) or "(none)")
        sys.exit(1)


if __name__ == "__main__":
    main()
