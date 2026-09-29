# Echo Shift

Install the project and its dependencies with `uv sync`, then run the game with
`uv run echo_shift`. Run the full test suite with `uv run all_tests`.

Pyxel supports Windows, macOS and Linux. On Linux, run the game from a graphical
desktop session with the system's graphics and audio libraries available.

The prototype opens at the hub console. Use WASD or arrow keys to move, Space to
wait, Enter to start or commit a recording, Q to launch the echo, E to open the
power console, R to retry the launched recording, C to clear the chamber, and P
to pause. In the power console, use Up/Down to select a circuit, Space to
toggle it, Enter to apply, or E to close.

## Building for Windows

On Windows 11, from the repository root:

```powershell
uv sync
uv run python tools/stage_build.py
uv run pyxel package build/app build/app/main.py
Move-Item app.pyxapp build/app.pyxapp
uv run pyxel app2exe build/app.pyxapp
```

`app2exe` writes `dist/app/app.exe` with its bundled runtime under `_internal`.
The executable can run from any directory; saves and logs go to
`%APPDATA%\EchoShift`.
