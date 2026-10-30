"""Render the player character as launcher icons: a PNG for Linux, an ICO for Windows."""

import argparse
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/raw/player_idle_0.png"
SIZE = 512
MARGIN = 16
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--png", type=Path, default=ROOT / "packaging/linux/echo-shift.png"
    )
    parser.add_argument(
        "--ico", type=Path, default=ROOT / "packaging/windows/echo-shift.ico"
    )
    args = parser.parse_args()

    sprite = Image.open(SOURCE).convert("RGBA")
    alpha = sprite.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
    sprite = sprite.crop(alpha.getbbox())
    inner = SIZE - 2 * MARGIN
    scale = inner / max(sprite.size)
    sprite = sprite.resize(
        (round(sprite.width * scale), round(sprite.height * scale)), Image.LANCZOS
    )
    picture = Image.new("RGBA", (SIZE, SIZE))
    picture.paste(
        sprite, ((SIZE - sprite.width) // 2, (SIZE - sprite.height) // 2), sprite
    )
    for out in (args.png, args.ico):
        out.parent.mkdir(parents=True, exist_ok=True)
    picture.save(args.png, optimize=True)
    picture.save(args.ico, sizes=[(n, n) for n in ICO_SIZES])
    print(f"Wrote {args.png} and {args.ico}")


if __name__ == "__main__":
    main()
