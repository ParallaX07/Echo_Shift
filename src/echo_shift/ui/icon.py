"""Pyxel-free window icon: a small palette-index picture cut from a sprite."""

from collections import Counter
from collections.abc import Callable

HEX = "0123456789abcdef"


def rows(
    pixel: Callable[[int, int], int], width: int, height: int, size: int = 16
) -> list[str]:
    """Shrink the opaque part of a sprite to `size` x `size` hex-digit rows.

    `pixel(x, y)` returns the palette index at a sprite pixel (0 is transparent).
    The sprite is cropped to its opaque bounds and centred in a square. Each icon
    pixel takes the most common colour of its block, or 0 when under half of the
    block is opaque, so the result uses only colours the sprite already has.
    """
    opaque = [(x, y) for y in range(height) for x in range(width) if pixel(x, y)]
    if not opaque:
        return ["0" * size] * size
    left, right = min(x for x, _ in opaque), max(x for x, _ in opaque) + 1
    top, bottom = min(y for _, y in opaque), max(y for _, y in opaque) + 1
    side = max(right - left, bottom - top)
    left -= (side - (right - left)) // 2
    top -= (side - (bottom - top)) // 2
    result = []
    for row in range(size):
        digits = ""
        for column in range(size):
            x0, x1 = left + column * side // size, left + (column + 1) * side // size
            y0, y1 = top + row * side // size, top + (row + 1) * side // size
            block = [
                pixel(x, y) if 0 <= x < width and 0 <= y < height else 0
                for y in range(y0, max(y1, y0 + 1))
                for x in range(x0, max(x1, x0 + 1))
            ]
            colours = Counter(c for c in block if c)
            digits += (
                HEX[colours.most_common(1)[0][0]]
                if colours and sum(colours.values()) * 2 >= len(block)
                else "0"
            )
        result.append(digits)
    return result
