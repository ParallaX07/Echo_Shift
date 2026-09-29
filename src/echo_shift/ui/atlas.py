"""Packed sprite lookup by id."""

import json

import pyxel

from echo_shift.paths import resource_path


class Atlas:
    def __init__(self) -> None:
        self.entries = json.loads(resource_path("assets", "atlas.json").read_text())
        pyxel.images[0].load(0, 0, str(resource_path("assets", "atlas.png")))

    def draw(self, sprite_id: str, x: int, y: int) -> None:
        sprite = self.entries[sprite_id]
        pyxel.blt(x, y, sprite["bank"], sprite["u"], sprite["v"], 32, 32, 0)
