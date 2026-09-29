"""Write review sheets, tile repeats and idle group GIFs."""

import json
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SIZE = 96


def main() -> None:
    assets = json.loads((ROOT / "assets/manifest.json").read_text())["assets"]
    images = [
        (
            asset,
            Image.open(ROOT / "assets/sprites" / f"{asset['id']}.png").convert("RGBA"),
        )
        for asset in assets
        if (ROOT / "assets/sprites" / f"{asset['id']}.png").exists()
    ]
    if not images:
        print("No processed sprites to preview.")
        return
    preview = ROOT / "assets/preview"
    preview.mkdir(parents=True, exist_ok=True)
    for scale, name in ((4, "contact_sheet.png"), (1, "contact_sheet_1x.png")):
        cell = SIZE * scale
        cell_width = max(cell, 112)
        row_height = cell + 14 * scale
        sheet = Image.new(
            "RGBA",
            (cell_width * 4, row_height * ((len(images) + 3) // 4)),
            "#777777",
        )
        draw = ImageDraw.Draw(sheet)
        for i, (asset, image) in enumerate(images):
            x, y = (i % 4) * cell_width, (i // 4) * row_height
            sprite_x = x + (cell_width - cell) // 2
            sheet.alpha_composite(
                image.resize((cell, cell), Image.Resampling.NEAREST), (sprite_x, y)
            )
            draw.text((x, y + cell), asset["id"], fill="white", stroke_width=0)
        sheet.save(preview / name)

    for asset, image in images:
        if asset["type"] == "tile":
            repeated = Image.new("RGBA", (SIZE * 3, SIZE * 3))
            for y in range(0, SIZE * 3, SIZE):
                for x in range(0, SIZE * 3, SIZE):
                    repeated.alpha_composite(image, (x, y))
            repeated.save(preview / f"{asset['id']}_repeat.png")

    groups = defaultdict(list)
    for asset, image in images:
        groups[asset["group"]].append((asset, image))
    for group, frames in groups.items():
        if len(frames) > 1:
            frames.sort(key=lambda pair: pair[0]["id"])
            frames[0][1].save(
                preview / f"{group}.gif",
                save_all=True,
                append_images=[frame for _, frame in frames[1:]],
                duration=350,
                loop=0,
                disposal=2,
            )


if __name__ == "__main__":
    main()
