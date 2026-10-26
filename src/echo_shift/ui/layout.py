"""Screen measurements shared by game and overlay drawing."""

import math
from dataclasses import dataclass

from echo_shift.engine.model import Chamber, TileType

Rect = tuple[int, int, int, int]
FONT_ADVANCE = 0.602  # DejaVu Sans Mono advance in em; the width is rounded up.


def font_size(scale: int) -> int:
    return max(12, scale * 6 + 4)


def char_width(scale: int) -> int:
    """Pixel width of one monospaced character, never narrower than the font."""
    return math.ceil(font_size(scale) * FONT_ADVANCE)


def line_height(scale: int) -> int:
    return max(9 * scale, font_size(scale) + 2)


def text_width(value: str, scale: int) -> int:
    return len(value) * char_width(scale)


def elide(value: str, width: int, scale: int) -> str:
    """Shorten `value` with "..." so it fits in `width` pixels."""
    room = max(0, width // char_width(scale))
    if len(value) <= room:
        return value
    return value[:room] if room <= 3 else value[: room - 3] + "..."


def route_bounds(chamber: Chamber) -> tuple[int, int, int, int]:
    """(min_x, min_y, max_x, max_y) of the traversable tiles."""
    cells = [
        (x, y)
        for y, row in enumerate(chamber.tiles)
        for x, tile in enumerate(row)
        if tile is not TileType.WALL
    ]
    xs, ys = [x for x, _ in cells], [y for _, y in cells]
    return min(xs), min(ys), max(xs), max(ys)


def framed_bounds(chamber: Chamber) -> tuple[int, int, int, int]:
    """The traversable area plus a one-tile wall border, clipped to the grid."""
    min_x, min_y, max_x, max_y = route_bounds(chamber)
    return (
        max(0, min_x - 1),
        max(0, min_y - 1),
        min(len(chamber.tiles[0]) - 1, max_x + 1),
        min(len(chamber.tiles) - 1, max_y + 1),
    )


@dataclass(frozen=True)
class Layout:
    """Top bar, room and bottom bar for one window size.

    `cell` is the reference tile size used to scale paddings; the room's own
    tile size comes from `room_fit`.
    """

    width: int
    height: int
    cell: int
    text_scale: int
    top: Rect
    room: Rect
    bottom: Rect

    @classmethod
    def fit(cls, width: int, height: int, text_scale: int | None = None) -> "Layout":
        cell = max(1, min(height // 9, width // 16))
        scale = text_scale or max(1, round(cell / 48))
        pad = 3 * scale
        row = line_height(scale) + pad
        top_h = 2 * row + 3 * pad
        bottom_h = 24 * scale + row + 3 * pad
        room_h = max(1, height - top_h - bottom_h)
        return cls(
            width,
            height,
            cell,
            scale,
            (0, 0, width, top_h),
            (0, top_h, width, room_h),
            (0, top_h + room_h, width, bottom_h),
        )

    @property
    def room_x(self) -> int:
        return self.room[0]

    @property
    def room_y(self) -> int:
        return self.room[1]

    @property
    def room_w(self) -> int:
        return self.room[2]

    @property
    def room_h(self) -> int:
        return self.room[3]

    @property
    def pad(self) -> int:
        return 3 * self.text_scale

    @property
    def row_h(self) -> int:
        return line_height(self.text_scale) + self.pad

    @property
    def slot(self) -> int:
        return 24 * self.text_scale

    def top_rows(self) -> tuple[Rect, Rect]:
        x, y, w, _ = self.top
        pad = self.pad
        return (
            (x + pad, y + pad, w - 2 * pad, self.row_h),
            (x + pad, y + 2 * pad + self.row_h, w - 2 * pad, self.row_h),
        )

    def bottom_rows(self) -> tuple[Rect, Rect]:
        x, y, w, _ = self.bottom
        pad = self.pad
        return (
            (x + pad, y + pad, w - 2 * pad, self.slot),
            (x + pad, y + 2 * pad + self.slot, w - 2 * pad, self.row_h),
        )

    @property
    def drawer_width(self) -> int:
        wide = max(
            self.width * 3 // 10, 26 * char_width(self.text_scale) + 4 * self.pad
        )
        return min(self.width * 2 // 5, wide)

    def console_drawer(self) -> Rect:
        """The power console's strip along the right edge of the room band."""
        return (
            self.width - self.drawer_width,
            self.room_y,
            self.drawer_width,
            self.room_h,
        )

    def room_fit(
        self, columns: int, rows: int, console: bool = False
    ) -> tuple[int, int, int]:
        """Largest square cell for a `columns` x `rows` block of tiles.

        Returns (cell, x, y) with the block centred in the room. While the
        console is open the block is fitted left of the drawer instead.
        """
        x, y, w, h = self.room
        if console:
            w -= self.drawer_width + self.pad
        cell = max(1, min(w // columns, h // rows))
        return cell, x + (w - columns * cell) // 2, y + (h - rows * cell) // 2

    def overlay(self) -> tuple[int, int, int, int]:
        width = min(self.width - 32, max(420, self.width * 3 // 5))
        height = min(self.room_h - 16, max(280, self.height * 3 // 5))
        return (
            (self.width - width) // 2,
            self.room_y + (self.room_h - height) // 2,
            width,
            height,
        )

    def menu_rect(
        self, x: int, y: int, width: int, height: int
    ) -> tuple[int, int, int, int]:
        scale = min(self.width / 1280, self.height / 720)
        left = (self.width - round(1280 * scale)) // 2
        top = (self.height - round(720 * scale)) // 2
        return (
            left + round(x * scale),
            top + round(y * scale),
            round(width * scale),
            round(height * scale),
        )

    def start_button(self) -> tuple[int, int, int, int]:
        return self.menu_rect(480, 560, 320, 64)

    def chamber_cards(self, count: int) -> tuple[tuple[int, int, int, int], ...]:
        columns = min(3, count)
        rows = (count + 2) // 3
        card_height = 320 if rows == 1 else 188
        top = 214 if rows == 1 else 185
        left = (1280 - (columns * 300 + (columns - 1) * 24)) // 2
        return tuple(
            self.menu_rect(
                left + (index % 3) * 324,
                top + (index // 3) * (card_height + 18),
                300,
                card_height,
            )
            for index in range(count)
        )
