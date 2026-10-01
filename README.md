# Echo Shift

Install the project and its dependencies with `uv sync`, then run the game with
`uv run echo_shift`. Run the full test suite with `uv run all_tests`.

Pyxel supports Windows, macOS and Linux. On Linux, run the game from a graphical
desktop session with the system's graphics and audio libraries available.

The title screen opens a level select screen. Click Start or press Enter, then
use WASD/arrow keys and Enter or the mouse to choose an unlocked chamber.
Each chamber offers a guided lesson (Enter) or free play (F). Guided lessons
explain and check each action; acknowledge a step with Enter, then perform it
with a separate key press. Press T for keyboard-accessible contextual help,
hover objects and HUD fields for live explanations, or H for counted hints.
See [the guided lesson controls](docs/tutorials.md). Progress is saved as `progress.json` in
the per-user data directory.

For playtests, each chamber visit is written to `playtest.jsonl` in that same
directory when it ends or the game closes.

During play, use WASD or arrow keys to move, Space to wait, Enter to start or
commit a recording, Q to launch the echo, E to open the power console, R to
retry the launched recording, C to restart, P to pause, L for level select,
and M to toggle mute. At the console, use Up/Down to select a circuit, Space
to toggle it, Enter to apply, or E to close.

The game starts windowed at up to 1280×720. Press F11 or Alt+Enter to toggle
fullscreen; the complete room stays on the left with status and timeline on
the right.

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
