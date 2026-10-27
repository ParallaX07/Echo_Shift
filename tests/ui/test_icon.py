"""The window icon is a small hex-digit picture cut from the player sprite."""

import json
from pathlib import Path

from PIL import Image

from echo_shift.ui import icon

ROOT = Path(__file__).resolve().parents[2]


def sprite_indices(name):
    colors = json.loads((ROOT / "assets/palette.json").read_text())["colors"]
    lookup = {
        tuple(int(c["hex"][i : i + 2], 16) for i in (1, 3, 5)): n
        for n, c in enumerate(colors)
    }
    image = Image.open(ROOT / "assets/sprites" / f"{name}.png").convert("RGBA")
    return lambda x, y: (
        lookup[image.getpixel((x, y))[:3]] if image.getpixel((x, y))[3] else 0
    )


def test_the_player_icon_is_square_transparent_and_uses_palette_digits():
    rows = icon.rows(sprite_indices("player_idle_0"), 96, 96, 32)
    assert len(rows) == 32 and all(len(row) == 32 for row in rows)
    text = "".join(rows)
    assert set(text) <= set(icon.HEX)
    assert "9" in text  # the amber jacket
    assert text.count("0") > text.count("9")  # background stays transparent
    assert set(rows[0]) != {"0"} and set(rows[-1]) != {"0"}  # cropped to the figure


def test_a_blank_sprite_gives_a_transparent_icon():
    assert icon.rows(lambda x, y: 0, 96, 96, 4) == ["0000"] * 4


def test_an_icon_is_deterministic():
    pixel = sprite_indices("player_idle_0")
    assert icon.rows(pixel, 96, 96, 16) == icon.rows(pixel, 96, 96, 16)
