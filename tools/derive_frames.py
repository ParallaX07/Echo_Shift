"""Write sprites derived from approved ones through deterministic pixel operations.

Usage: uv run python tools/derive_frames.py [id ...]

A manifest entry with `"source": "derived"` names its parent in `from`, an
operation in `op` and the operation's arguments in `params`. No generation is
involved: the same parent and parameters always give the same PNG.
"""

import json
import sys
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


OPS = {"copy": copy, "rotate": rotate}


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
