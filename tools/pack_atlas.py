"""Pack processed sprites into the single 256x256 Pyxel image bank."""

import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    palette_data = json.loads((ROOT / "assets/palette.json").read_text())
    colors = [tuple(bytes.fromhex(item["hex"][1:])) for item in palette_data["colors"]]
    palette = [channel for color in colors for channel in color] + [0] * (768 - 48)
    manifest = json.loads((ROOT / "assets/manifest.json").read_text())["assets"]
    atlas = Image.new("P", (256, 256), 0)
    atlas.putpalette(palette)
    entries = {}
    for index, asset in enumerate(manifest):
        path = ROOT / "assets/sprites" / f"{asset['id']}.png"
        if not path.exists():
            continue
        x, y = (index % 8) * 32, (index // 8) * 32
        rgba = Image.open(path).convert("RGBA")
        pixels = []
        for r, g, b, alpha in rgba.getdata():
            pixels.append(0 if alpha == 0 else colors.index((r, g, b)))
        tile = Image.new("P", (32, 32), 0)
        tile.putpalette(palette)
        tile.putdata(pixels)
        atlas.paste(tile, (x, y))
        entries[asset["id"]] = {"bank": 0, "u": x, "v": y, "width": 32, "height": 32}
    (ROOT / "assets/atlas.png").parent.mkdir(parents=True, exist_ok=True)
    atlas.save(ROOT / "assets/atlas.png")
    (ROOT / "assets/atlas.json").write_text(json.dumps(entries, indent=2) + "\n")


if __name__ == "__main__":
    main()
