"""Validate processed sprites against the locked format and palette."""

import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def validate() -> list[str]:
    palette_data = json.loads((ROOT / "assets/palette.json").read_text())
    palette = {
        tuple(bytes.fromhex(color["hex"][1:])) for color in palette_data["colors"][1:]
    }
    minimums = palette_data["minimum_opaque_pixels"]
    assets = json.loads((ROOT / "assets/manifest.json").read_text())["assets"]
    errors = []
    for asset in assets:
        path = ROOT / "assets/sprites" / f"{asset['id']}.png"
        if not path.exists():
            if asset["status"] == "ok":
                errors.append(f"{asset['id']}: approved sprite is missing")
            continue
        image = Image.open(path)
        if image.size != (32, 32) or image.mode != "RGBA":
            errors.append(f"{asset['id']}: expected 32x32 RGBA")
            continue
        pixels = list(image.get_flattened_data())
        alpha = {pixel[3] for pixel in pixels}
        if not alpha <= {0, 255}:
            errors.append(f"{asset['id']}: alpha must be binary")
        opaque = [pixel for pixel in pixels if pixel[3] == 255]
        if not opaque:
            errors.append(f"{asset['id']}: sprite is blank")
            continue
        if any(pixel[:3] not in palette for pixel in opaque):
            errors.append(
                f"{asset['id']}: opaque pixels use colours outside the palette"
            )
        if len(opaque) < minimums[asset["type"]]:
            errors.append(
                f"{asset['id']}: {len(opaque)} opaque pixels; needs {minimums[asset['type']]}"
            )
        if asset["id"].startswith("echo_") and (29, 173, 255) not in {
            pixel[:3] for pixel in opaque
        }:
            errors.append(f"{asset['id']}: echo outline colour #29ADFF is missing")
    return errors


def validate_manifest() -> list[str]:
    assets = json.loads((ROOT / "assets/manifest.json").read_text())["assets"]
    atlas_path = ROOT / "assets/atlas.json"
    atlas = json.loads(atlas_path.read_text()) if atlas_path.exists() else {}
    return [
        f"{asset['id']}: approved asset needs both sprite and atlas entry"
        for asset in assets
        if asset["status"] == "ok"
        and (
            not (ROOT / "assets/sprites" / f"{asset['id']}.png").exists()
            or asset["id"] not in atlas
        )
    ]


if __name__ == "__main__":
    problems = validate() + validate_manifest()
    if problems:
        raise SystemExit("\n".join(problems))
    print("Asset validation passed.")
