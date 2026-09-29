"""Crop, fit and palette-snap one manifest asset into a 96×96 PNG."""

import json
import sys
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
RESAMPLE = Image.Resampling.NEAREST
SIZE = 96


def _palette() -> list[tuple[int, int, int]]:
    data = json.loads((ROOT / "assets/palette.json").read_text())
    return [tuple(bytes.fromhex(c["hex"][1:])) for c in data["colors"]]


def _manifest() -> dict[str, dict]:
    return {
        asset["id"]: asset
        for asset in json.loads((ROOT / "assets/manifest.json").read_text())["assets"]
    }


def _open(asset: dict) -> Image.Image:
    image = Image.open(ROOT / "assets/raw" / f"{asset['id']}.png").convert("RGBA")
    if asset.get("source", "alpha") == "key":
        image.putdata(
            [
                (
                    *pixel[:3],
                    0
                    if pixel[0] > 230 and pixel[2] > 230 and pixel[1] < 40
                    else pixel[3],
                )
                for pixel in image.get_flattened_data()
            ]
        )
    return image


def _bounds(image: Image.Image) -> tuple[int, int, int, int]:
    mask = image.getchannel("A").point(lambda alpha: 255 if alpha >= 128 else 0)
    bounds = mask.getbbox()
    if bounds is None:
        raise ValueError("source contains no visible pixels")
    return bounds


def _save(
    asset: dict, source: Image.Image, palette: list[tuple[int, int, int]], scale=None
) -> Path:
    if asset["type"] == "tile":
        if asset.get("mirror_edges"):
            quarter = source.resize((SIZE // 2, SIZE // 2), RESAMPLE)
            small = Image.new("RGBA", (SIZE, SIZE))
            small.paste(quarter, (0, 0))
            small.paste(ImageOps.mirror(quarter), (SIZE // 2, 0))
            small.paste(ImageOps.flip(quarter), (0, SIZE // 2))
            small.paste(ImageOps.flip(ImageOps.mirror(quarter)), (SIZE // 2, SIZE // 2))
        else:
            small = source.resize((SIZE, SIZE), RESAMPLE)
        offset = (0, 0)
    else:
        own_bounds = _bounds(source)
        subject = source.crop(own_bounds)
        width = max(1, round(subject.width * scale))
        height = max(1, round(subject.height * scale))
        small = subject.resize((width, height), RESAMPLE)
        offset = (SIZE // 2 - round(width / 2), 87 - height)

    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    canvas.alpha_composite(small, offset)
    pixels = []
    for r, g, b, alpha in canvas.get_flattened_data():
        if alpha < 128:
            pixels.append((0, 0, 0, 0))
        else:
            rgb = min(
                palette,
                key=lambda color: sum((x - y) ** 2 for x, y in zip((r, g, b), color)),
            )
            pixels.append((*rgb, 255))
    canvas.putdata(pixels)
    output = ROOT / "assets/sprites" / f"{asset['id']}.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)
    return output


def process(asset_id: str) -> Path:
    manifest = _manifest()
    if asset_id not in manifest:
        raise ValueError(f"unknown asset id: {asset_id}")
    asset = manifest[asset_id]
    palette = _palette()[1:]
    grouped = [a for a in manifest.values() if a["group"] == asset["group"]]
    raw_group = [
        a for a in grouped if (ROOT / "assets/raw" / f"{a['id']}.png").exists()
    ]
    if asset["type"] == "tile":
        return _save(asset, _open(asset), palette)
    frames = [(a, _open(a)) for a in raw_group]
    bounds = [_bounds(frame) for _, frame in frames]
    scale = min(
        (SIZE - 12) / max(box[2] - box[0] for box in bounds),
        (87 - 6) / max(box[3] - box[1] for box in bounds),
    )
    outputs = {a["id"]: _save(a, frame, palette, scale) for a, frame in frames}
    return outputs[asset_id]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: uv run python tools/process_asset.py ASSET_ID")
    print(process(sys.argv[1]))
