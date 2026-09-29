import subprocess
import sys


def test_engine_import_does_not_import_pyxel() -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, echo_shift.engine; assert 'pyxel' not in sys.modules",
        ],
        check=True,
    )
