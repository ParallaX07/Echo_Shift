"""Safe and unsafe floor differ by texture, not only by colour or brightness.

A player who cannot tell the colours apart sees the floor in grey. Brightness
alone is a weak cue (the calm hub floor is about as bright as dark floor), so
the tiles are compared by their binarised gradient maps: where the grey level
changes sharply. A uniform brightness shift cannot change that map.
"""

import json
from pathlib import Path

from PIL import Image

from echo_shift.ui.app import DARK_REMAP

ROOT = Path(__file__).resolve().parents[2]
EDGE = 15  # grey-level step (0-255) that counts as an edge
SAFE = ("floor_hub", "floor_hub_inner", "floor_lit")
MIN_DIFFERENT = 0.08  # share of gradient positions where the edge maps disagree


def palette():
    colors = json.loads((ROOT / "assets/palette.json").read_text())["colors"]
    return [tuple(int(c["hex"][i : i + 2], 16) for i in (1, 3, 5)) for c in colors]


def indices(name):
    """A sprite as rows of palette indices."""
    lookup = {rgb: index for index, rgb in enumerate(palette())}
    image = Image.open(ROOT / "assets/sprites" / f"{name}.png").convert("RGBA")
    return [
        [lookup[image.getpixel((x, y))[:3]] for x in range(image.width)]
        for y in range(image.height)
    ]


def grey(rows):
    """Rec. 601 luma of every pixel, as the grayscale render shows it."""
    luma = [0.299 * r + 0.587 * g + 0.114 * b for r, g, b in palette()]
    return [[luma[i] for i in row] for row in rows]


def edge_map(levels, offset=0.0):
    """Positions where the grey level steps by more than EDGE (right and down)."""
    height, width = len(levels), len(levels[0])
    edges = set()
    for y in range(height):
        for x in range(width):
            here = levels[y][x] + offset
            if x + 1 < width and abs(levels[y][x + 1] + offset - here) > EDGE:
                edges.add((x, y, "x"))
            if y + 1 < height and abs(levels[y + 1][x] + offset - here) > EDGE:
                edges.add((x, y, "y"))
    return edges


def difference(a, b):
    cells = 2 * len(a) * len(a[0])
    return len(edge_map(a) ^ edge_map(b)) / cells


def dark(name):
    return [[DARK_REMAP[i] for i in row] for row in indices(name)]


def test_the_texture_measure_ignores_a_uniform_brightness_shift():
    levels = grey(indices("floor_lit"))
    assert edge_map(levels) == edge_map(levels, offset=-60.0)
    assert difference(levels, [[v + 40 for v in row] for row in levels]) == 0


def test_every_safe_floor_differs_in_texture_from_the_dark_floor():
    unsafe = grey(dark("floor_lit"))
    for name in SAFE:
        safe = grey(indices(name))
        assert difference(safe, unsafe) >= MIN_DIFFERENT, name


def test_the_calm_hub_floor_is_not_told_apart_by_brightness_alone():
    """The pairs that are close in mean grey are the ones texture must carry."""
    unsafe = grey(dark("floor_lit"))
    inner = grey(indices("floor_hub_inner"))

    def mean(levels):
        return sum(map(sum, levels)) / (len(levels) * len(levels[0]))

    assert abs(mean(inner) - mean(unsafe)) < 25
    assert difference(inner, unsafe) >= MIN_DIFFERENT


def test_safe_floor_is_busier_than_dark_floor_in_grey():
    unsafe = len(edge_map(grey(dark("floor_lit"))))
    for name in SAFE:
        assert len(edge_map(grey(indices(name)))) > 1.5 * unsafe, name


CONDUITS = ("conduit_off", "conduit_live")


def test_live_conduit_off_conduit_and_floor_differ_in_texture_not_only_hue():
    floors = {name: grey(indices(name)) for name in ("floor_lit", *CONDUITS)}
    assert difference(floors["conduit_live"], floors["conduit_off"]) >= MIN_DIFFERENT
    for name in CONDUITS:
        assert difference(floors[name], floors["floor_lit"]) >= MIN_DIFFERENT, name


def test_a_live_conduit_is_busier_and_brighter_than_an_idle_one_in_grey():
    live, off = (grey(indices(name)) for name in reversed(CONDUITS))

    def mean(levels):
        return sum(map(sum, levels)) / (len(levels) * len(levels[0]))

    assert len(edge_map(live)) > 1.3 * len(edge_map(off))
    assert mean(live) > mean(off)


def test_the_live_conduit_is_red_where_the_safe_hub_stripe_is_navy():
    """Hazard stripes mean the safe hub; a live conduit must not pass for one."""

    def share(name, colour):
        flat = [i for row in indices(name) for i in row]
        return flat.count(colour) / len(flat)

    assert share("conduit_live", 8) > 0.25
    assert share("floor_hub", 8) < 0.01
