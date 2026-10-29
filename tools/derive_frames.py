"""Write sprites derived from approved ones through deterministic pixel operations.

Usage: uv run python tools/derive_frames.py [id ...]

A manifest entry with `"source": "derived"` names its parent in `from`, an
operation in `op` and the operation's arguments in `params`. No generation is
involved: the same parent and parameters always give the same PNG.
"""

import json
import sys
from functools import cache
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
TURNS = {
    90: Image.Transpose.ROTATE_270,
    180: Image.Transpose.ROTATE_180,
    270: Image.Transpose.ROTATE_90,
}


def rotate(image: Image.Image, angle: int, box: list[int] | None = None) -> Image.Image:
    """Rotate clockwise by 90, 180 or 270 degrees, optionally only a square region.

    `box` is [x, y, size]; pixels outside it (for example a frame) stay put.
    """
    if angle not in TURNS:
        raise ValueError(f"rotate angle must be 90, 180 or 270, got {angle}")
    x, y, size = box or (0, 0, image.width)
    if (
        size < 1
        or x < 0
        or y < 0
        or x + size > image.width
        or y + size > image.height
        or (box is None and image.width != image.height)
    ):
        raise ValueError("rotate needs a square region inside the image")
    result = image.copy()
    region = image.crop((x, y, x + size, y + size)).transpose(TURNS[angle])
    result.paste(region, (x, y))
    return result


def copy(image: Image.Image) -> Image.Image:
    """Return the parent unchanged, so a frame set can share one id scheme."""
    return image.copy()


@cache
def palette() -> tuple[tuple[int, int, int], ...]:
    """The locked palette as RGB triples, indexed like assets/palette.json."""
    colors = json.loads((ROOT / "assets/palette.json").read_text())["colors"]
    return tuple(tuple(bytes.fromhex(color["hex"][1:])) for color in colors)


def colour(index: int) -> tuple[int, int, int, int]:
    """Opaque RGBA for a palette index; index 0 is the transparent key and never drawn."""
    if isinstance(index, bool) or not isinstance(index, int) or not 1 <= index <= 15:
        raise ValueError(f"palette index must be 1-15, got {index!r}")
    return (*palette()[index], 255)


def opaque_bounds(image: Image.Image) -> tuple[int, int, int, int]:
    bounds = image.getchannel("A").getbbox()
    if bounds is None:
        raise ValueError("image is blank")
    return bounds


def offset(image: Image.Image, dx: int = 0, dy: int = 0) -> Image.Image:
    """Shift every pixel by (dx, dy); whatever leaves the 96x96 frame is clipped.

    A vertical shift moves the feet baseline, so frames that must keep it use
    `squash` or a horizontal shift instead.
    """
    result = Image.new("RGBA", image.size)
    result.paste(image, (dx, dy))
    return result


def squash(
    image: Image.Image, rows: int, baseline: int = 87, top: int | None = None
) -> Image.Image:
    """Drop `rows` evenly spaced pixel rows (a negative count duplicates rows).

    The rows between `top` (default: the first opaque row) and `baseline`
    (exclusive) are resampled so the last row, the feet, stays where it is and
    the sprite gets shorter (or taller) from the head down.
    """
    top = opaque_bounds(image)[1] if top is None else top
    height = baseline - top
    new_height = height - rows
    if height < 1 or new_height < 1 or baseline - new_height < 0:
        raise ValueError("squash rows leave no sprite inside the frame")
    result = image.copy()
    result.paste((0, 0, 0, 0), (0, top, image.width, baseline))
    for j in range(new_height):
        source = baseline - 1 - (j * height) // new_height
        row = image.crop((0, source, image.width, source + 1))
        result.paste(row, (0, baseline - 1 - j))
    return result


def palette_swap(image: Image.Image, map: dict | list) -> Image.Image:
    """Recolour opaque pixels by palette index.

    `map` is {"from": to} (JSON keys are strings) or [[from, to], ...], using
    indices from assets/palette.json. Targets are 1-15: index 0 is never drawn.
    Pixels of any other colour stay as they are.
    """
    pairs = map.items() if isinstance(map, dict) else map
    swaps = {palette()[int(old)]: colour(new) for old, new in pairs}
    result = image.copy()
    pixels = result.load()
    for y in range(image.height):
        for x in range(image.width):
            pixel = pixels[x, y]
            if pixel[3] and pixel[:3] in swaps:
                pixels[x, y] = swaps[pixel[:3]]
    return result


def mix(x: int, y: int, seed: int) -> int:
    """Platform-independent integer hash of a cell, used to order dissolve cells."""
    h = (x * 374761393 + y * 668265263 + seed * 2246822519) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return h ^ (h >> 16)


def dissolve(
    image: Image.Image, step: int, steps: int, seed: int = 0, cell: int = 3
) -> Image.Image:
    """Remove `step`/`steps` of the opaque pixels in a seeded dither of cell x cell blocks.

    Cells go in hash order, so a larger step always removes a superset of what
    a smaller step with the same seed removes. The lowest opaque row never
    dissolves, which keeps the feet anchor.
    """
    if steps < 1 or not 0 <= step <= steps or cell < 1:
        raise ValueError("dissolve needs 0 <= step <= steps and cell >= 1")
    pixels = image.load()
    floor = opaque_bounds(image)[3] - 1
    cells: dict[tuple[int, int], list[tuple[int, int]]] = {}
    total = 0
    for y in range(image.height):
        for x in range(image.width):
            if pixels[x, y][3]:
                total += 1
                if y != floor:
                    cells.setdefault((x // cell, y // cell), []).append((x, y))
    target = (total * step + steps // 2) // steps
    result = image.copy()
    out = result.load()
    removed = 0
    for key in sorted(cells, key=lambda k: (mix(*k, seed), k)):
        if removed >= target:
            break
        for x, y in cells[key]:
            out[x, y] = (0, 0, 0, 0)
        removed += len(cells[key])
    return result


def slide(image: Image.Image, moves: list[dict], behind: bool = False) -> Image.Image:
    """Move the opaque pixels of boxes by (dx, dy), leaving transparency behind.

    Each move is {"box": [x, y, w, h], "dx": int, "dy": int}. Every box is
    read from the parent, so moves do not affect each other. With `behind`,
    moved pixels only land on transparent pixels, as if passing behind what
    is already there (a gate leaf retracting into its post).
    """
    result = image.copy()
    out = result.load()
    carried = []
    for move in moves:
        x, y, w, h = move["box"]
        if (
            w < 1
            or h < 1
            or x < 0
            or y < 0
            or x + w > image.width
            or y + h > image.height
        ):
            raise ValueError(f"slide box {move['box']} is outside the image")
        region = image.crop((x, y, x + w, y + h))
        carried.append((region, x + move.get("dx", 0), y + move.get("dy", 0)))
        result.paste((0, 0, 0, 0), (x, y, x + w, y + h))
    for region, left, top in carried:
        source = region.load()
        for j in range(region.height):
            for i in range(region.width):
                x, y = left + i, top + j
                if (
                    source[i, j][3]
                    and 0 <= x < image.width
                    and 0 <= y < image.height
                    and not (behind and out[x, y][3])
                ):
                    out[x, y] = source[i, j]
    return result


def ring(
    image: Image.Image, index: int, margin: int = 6, baseline: int = 87
) -> Image.Image:
    """Add a one-pixel outline of palette `index` just outside the silhouette.

    Only transparent pixels that touch an opaque one (up, down, left, right)
    are drawn, and only inside the safe margin and above the feet baseline, so
    the sprite keeps its anchor.
    """
    glow = colour(index)
    result = image.copy()
    out = result.load()
    source = image.load()
    for y in range(margin, min(baseline, image.height - margin)):
        for x in range(margin, image.width - margin):
            if source[x, y][3]:
                continue
            if any(
                0 <= x + dx < image.width
                and 0 <= y + dy < image.height
                and source[x + dx, y + dy][3]
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            ):
                out[x, y] = glow
    return result


def stamp(
    image: Image.Image,
    rows: list[str],
    legend: dict[str, int],
    scale: int = 3,
    x: int = 0,
    y: int = 0,
    clear: bool = False,
) -> Image.Image:
    """Paint a small pixel map over the parent, each map pixel `scale` x `scale`.

    `rows` are equal-length strings; a character found in `legend` paints that
    palette index (1-15), any other character leaves the parent as it is. With
    `clear` the parent is wiped first, so it only fixes the shared scale and
    anchor. The map starts at (x, y) and must fit inside the image.
    """
    width = len(rows[0]) if rows else 0
    if (
        not width
        or scale < 1
        or any(len(row) != width for row in rows)
        or x < 0
        or y < 0
        or x + width * scale > image.width
        or y + len(rows) * scale > image.height
    ):
        raise ValueError("stamp needs equal-length rows that fit inside the image")
    result = Image.new("RGBA", image.size) if clear else image.copy()
    for j, row in enumerate(rows):
        for i, char in enumerate(row):
            if char in legend:
                result.paste(
                    colour(legend[char]),
                    (
                        x + i * scale,
                        y + j * scale,
                        x + (i + 1) * scale,
                        y + (j + 1) * scale,
                    ),
                )
    return result


OPS = {
    "copy": copy,
    "rotate": rotate,
    "offset": offset,
    "squash": squash,
    "palette_swap": palette_swap,
    "dissolve": dissolve,
    "slide": slide,
    "ring": ring,
    "stamp": stamp,
}


def manifest() -> dict[str, dict]:
    return {
        asset["id"]: asset
        for asset in json.loads((ROOT / "assets/manifest.json").read_text())["assets"]
    }


def derive(asset: dict, root: Path = ROOT) -> Image.Image:
    parent = Image.open(root / "assets/sprites" / f"{asset['from']}.png").convert(
        "RGBA"
    )
    return OPS[asset["op"]](parent, **asset.get("params", {}))


def main(ids: list[str]) -> None:
    assets = manifest()
    derived = [a for a in assets.values() if a.get("source") == "derived"]
    if ids:
        missing = [i for i in ids if i not in assets or assets[i] not in derived]
        if missing:
            raise SystemExit(f"not derived manifest entries: {', '.join(missing)}")
        derived = [assets[i] for i in ids]
    for asset in derived:
        path = ROOT / "assets/sprites" / f"{asset['id']}.png"
        derive(asset).save(path)
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])
