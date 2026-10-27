"""The packed atlas exceeds the legacy image bank and retains entry geometry."""

import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from echo_shift.ui import atlas


def test_atlas_loads_full_image_and_draws_entry_size(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    entries = json.loads((root / "assets/atlas.json").read_text())
    with Image.open(root / "assets/atlas.png") as image:
        assert image.width == 8 * 96
        assert image.height > 256
        for entry in entries.values():
            assert entry["u"] + entry["width"] <= image.width
            assert entry["v"] + entry["height"] <= image.height
            assert (entry["width"], entry["height"]) == (96, 96)
    made = []
    drawn = []

    class FakeImage:
        def __init__(self, width, height):
            made.append((width, height))

        def load(self, *args):
            pass

    monkeypatch.setattr(
        atlas,
        "pyxel",
        SimpleNamespace(
            Image=FakeImage, blt=lambda *args, **kwargs: drawn.append((args, kwargs))
        ),
    )
    atlas.Atlas().draw("player_idle_0", 10, 20, 80)
    assert made[0][0] == 768 and made[0][1] > 256
    assert drawn[0][0][5:7] == (96, 96)
    assert drawn[0][1]["scale"] == 80 / 96
    atlas.Atlas().draw("player_idle_0", 10, 20, 80, 1.25)  # a pop grows it in place
    assert drawn[1][0][:2] == drawn[0][0][:2]
    assert drawn[1][1]["scale"] == 80 / 96 * 1.25


def test_approved_idle_frames_share_their_baseline_and_bounds():
    root = Path(__file__).resolve().parents[2]
    for group in ("player", "echo"):
        bounds = [
            Image.open(root / "assets/sprites" / f"{group}_idle_{frame}.png")
            .getchannel("A")
            .getbbox()
            for frame in (0, 1)
        ]
        assert all(top >= 6 and bottom == 87 for _, top, _, bottom in bounds)
        assert all(abs(a - b) <= 1 for a, b in zip(bounds[0], bounds[1]))
