"""Screen measurements shared by game and overlay drawing."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Layout:
    width: int
    height: int
    cell: int
    room_x: int
    room_y: int
    room_w: int
    room_h: int
    panel_x: int
    panel_y: int
    panel_w: int
    panel_h: int
    text_scale: int

    @classmethod
    def fit(cls, width: int, height: int, columns: int = 12, rows: int = 9) -> "Layout":
        # The reference room uses 75% of the width and the full height.
        cell = max(1, min(height // rows, width // (columns + columns // 3)))
        room_w, room_h = columns * cell, rows * cell
        room_y = (height - room_h) // 2
        panel_x = room_w
        text_scale = max(1, round(cell / 48))
        return cls(
            width,
            height,
            cell,
            0,
            room_y,
            room_w,
            room_h,
            panel_x,
            0,
            width - panel_x,
            height,
            text_scale,
        )

    def panel_content(self) -> tuple[int, int, int]:
        width = min(self.panel_w - 24, max(240, self.cell * 4 - 24))
        return self.panel_x + (self.panel_w - width) // 2, 12, width

    def overlay(self) -> tuple[int, int, int, int]:
        width = min(self.width - 32, max(420, self.width * 3 // 5))
        height = min(self.height - 32, max(260, self.height * 2 // 3))
        return (self.width - width) // 2, (self.height - height) // 2, width, height

    def timeline_slots(self) -> tuple[tuple[int, int, int], ...]:
        x, _, width = self.panel_content()
        unit = self.cell / 96
        top = round(565 * unit)
        gap = max(4, round(7 * unit))
        slot = min(
            round(63 * unit),
            (width - 2 * gap) // 3,
            (self.height - top - 12 - 3 * gap) // 4,
        )
        slot = max(1, slot)
        return tuple(
            (x + col * (slot + gap), top + row * (slot + gap), slot)
            for row in range(4)
            for col in range(3)
        )
