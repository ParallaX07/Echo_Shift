"""Launch the Pyxel feasibility window."""

import json

import pyxel

from echo_shift.paths import resource_path, user_data_dir
from echo_shift.spike import status_text

PICO8_PALETTE = [
    0x000000,
    0x1D2B53,
    0x7E2553,
    0x008751,
    0xAB5236,
    0x5F574F,
    0xC2C3C7,
    0xFFF1E8,
    0xFF004D,
    0xFFA300,
    0xFFEC27,
    0x00E436,
    0x29ADFF,
    0x83769C,
    0xFF77A8,
    0xFFCCAA,
]


def main() -> None:
    data = json.loads(resource_path("levels", "spike.json").read_text())
    pyxel.colors[:] = PICO8_PALETTE
    pyxel.init(384, 352, title="Echo Shift Feasibility Spike")
    pyxel.images[0].load(0, 0, str(resource_path("assets", "atlas.png")))
    (user_data_dir() / "phase0.txt").write_text("packaged resource smoke test\n")

    def draw() -> None:
        pyxel.cls(1)
        pyxel.blt(160, 128, 0, 0, 0, 32, 32, 0)
        pyxel.text(8, 8, status_text(), 7)
        pyxel.text(8, 20, data["purpose"], 7)

    pyxel.run(lambda: None, draw)


if __name__ == "__main__":
    main()
