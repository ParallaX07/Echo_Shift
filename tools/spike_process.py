"""Compare box, nearest, and block-majority downscaling at native size."""

from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PALETTE = [
    "#000000",
    "#1D2B53",
    "#7E2553",
    "#008751",
    "#AB5236",
    "#5F574F",
    "#C2C3C7",
    "#FFF1E8",
    "#FF004D",
    "#FFA300",
    "#FFEC27",
    "#00E436",
    "#29ADFF",
    "#83769C",
    "#FF77A8",
    "#FFCCAA",
]


def snap(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    colors = [tuple(bytes.fromhex(color[1:])) for color in PALETTE[1:]]
    return min(colors, key=lambda color: sum((a - b) ** 2 for a, b in zip(rgb, color)))


def majority(source: Image.Image) -> Image.Image:
    source = source.convert("RGBA")
    width, height = source.size
    output = Image.new("RGBA", (32, 32))
    pixels = source.load()
    for y in range(32):
        for x in range(32):
            block = [
                pixels[sx, sy]
                for sy in range(y * height // 32, (y + 1) * height // 32)
                for sx in range(x * width // 32, (x + 1) * width // 32)
            ]
            output.putpixel((x, y), Counter(block).most_common(1)[0][0])
    return output


def process(path: Path, key_magenta: bool) -> dict[str, Image.Image]:
    image = Image.open(path).convert("RGBA")
    if key_magenta:
        image.putdata(
            [
                (r, g, b, 0 if (r > 230 and b > 230 and g < 40) else a)
                for r, g, b, a in image.get_flattened_data()
            ]
        )
    alpha = image.getchannel("A")
    bounds = alpha.getbbox()
    if bounds is None:
        raise ValueError(f"no opaque subject found in {path}")
    image = image.crop(bounds)
    image.thumbnail((28, 28), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    canvas.alpha_composite(image, ((32 - image.width) // 2, (32 - image.height) // 2))
    results = {}
    for name, filter_ in (
        ("box", Image.Resampling.BOX),
        ("nearest", Image.Resampling.NEAREST),
    ):
        small = canvas.resize((32, 32), filter_)
        small.putdata(
            [
                (*snap(pixel[:3]), 255 if pixel[3] >= 128 else 0)
                for pixel in small.get_flattened_data()
            ]
        )
        results[name] = small
    pixelized = majority(canvas)
    pixelized.putdata(
        [
            (*snap(pixel[:3]), 255 if pixel[3] >= 128 else 0)
            for pixel in pixelized.get_flattened_data()
        ]
    )
    results["majority"] = pixelized
    return results


def main() -> None:
    samples = (
        (ROOT / "assets/spike/technician-transparent.png", False),
        (ROOT / "assets/spike/floor-magenta.png", True),
    )
    sheet = Image.new("RGB", (32 * 3, 32 * len(samples)), "#777777")
    for row, (path, keyed) in enumerate(samples):
        for column, (_, image) in enumerate(process(path, keyed).items()):
            sheet.paste(image, (column * 32, row * 32), image)
    output = ROOT / "assets/spike/filter-comparison.png"
    sheet.save(output)

    palette_colors = [tuple(bytes.fromhex(color[1:])) for color in PALETTE]
    atlas = Image.new("P", (256, 256), 0)
    atlas.putpalette(
        [channel for color in palette_colors for channel in color] + [0] * (768 - 48)
    )
    character = process(samples[0][0], False)["nearest"]
    indices = []
    for r, g, b, alpha in character.get_flattened_data():
        indices.append(
            0
            if alpha == 0
            else 1
            + min(
                range(15),
                key=lambda index: sum(
                    (a - b) ** 2 for a, b in zip((r, g, b), palette_colors[index + 1])
                ),
            )
        )
    atlas.putdata(indices + [0] * (256 * 256 - len(indices)))
    atlas.save(ROOT / "assets/spike/atlas.png")
    (ROOT / "assets/spike/atlas.json").write_text(
        '{"sample_character": {"bank": 0, "x": 0, "y": 0, "width": 32, "height": 32}}\n'
    )
    print(output)


if __name__ == "__main__":
    main()
