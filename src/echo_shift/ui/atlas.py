"""Packed sprite lookup by id."""

import json
import struct

import pyxel

from echo_shift.paths import resource_path


class Atlas:
    def __init__(self) -> None:
        self.entries = json.loads(resource_path("assets", "atlas.json").read_text())
        path = resource_path("assets", "atlas.png")
        with path.open("rb") as source:
            header = source.read(24)
        if header[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError("atlas image must be PNG")
        width, height = struct.unpack(">II", header[16:24])
        self.image = pyxel.Image(width, height)
        self.image.load(0, 0, str(path))
        for sprite_id, entry in self.entries.items():
            if (
                entry["u"] + entry["width"] > width
                or entry["v"] + entry["height"] > height
            ):
                raise ValueError(f"{sprite_id}: atlas entry exceeds image bounds")

    def draw(self, sprite_id: str, x: int, y: int, cell: int) -> None:
        sprite = self.entries[sprite_id]
        width, height = sprite["width"], sprite["height"]
        scale = cell / max(width, height)
        pyxel.blt(
            x + (cell - width) / 2,
            y + (cell - height) / 2,
            self.image,
            sprite["u"],
            sprite["v"],
            width,
            height,
            0,
            scale=scale,
        )
