"""Pyxel primitives for the in-world cues; the facts come from `cues`/`preview`.

Everything here uses palette indices only (never 0), draws over the room and
holds no state, so it can never change what a key does.
"""

from collections.abc import Callable
from itertools import pairwise

import pyxel

from echo_shift.engine.model import Position
from echo_shift.ui import camera, cues, motion
from echo_shift.ui.cues import ConsolePreview, DeviceLink

View = camera.View
Rect = camera.Rect
Text = Callable[..., None]  # text(x, y, value, color, scale)
RED, AMBER, YELLOW, GREEN, BLUE, GREY, LAVENDER, WHITE, NAVY = (
    8,
    9,
    10,
    11,
    12,
    5,
    13,
    7,
    1,
)


def tile(view: View, pos: Position) -> tuple[int, int, int, int]:
    cell, ox, oy = view
    return ox + pos.x * cell, oy + pos.y * cell, cell, cell


def centre(view: View, pos: Position) -> tuple[int, int]:
    x, y, cell, _ = tile(view, pos)
    return x + cell // 2, y + cell // 2


def path_dots(view: View, path: tuple[Position, ...]) -> None:
    """A faint dotted trail along the recorded echo path."""
    cell = view[0]
    size = max(3, cell // 22)
    pyxel.dither(0.6)
    for here, ahead in pairwise(path):
        if here == ahead:
            continue
        (x1, y1), (x2, y2) = centre(view, here), centre(view, ahead)
        for step in range(1, 5):
            x = x1 + (x2 - x1) * step // 4 - size // 2
            y = y1 + (y2 - y1) * step // 4 - size // 2
            pyxel.rect(x, y, size, size, BLUE)
    pyxel.dither(1.0)


def warning(view: View, pos: Position) -> None:
    """A triangle with an exclamation mark in the corner of a risky tile."""
    x, y, cell, _ = tile(view, pos)
    size = max(10, cell // 4)
    left, top = x + cell - size - 3, y + 3
    pyxel.tri(left + size // 2, top, left, top + size, left + size, top + size, RED)
    bar = max(2, size // 8)
    pyxel.rect(left + size // 2 - bar // 2, top + size // 3, bar, size // 3, WHITE)
    pyxel.rect(left + size // 2 - bar // 2, top + size * 3 // 4, bar, bar, WHITE)


def unsafe_outline(view: View, pos: Position, mark: bool) -> None:
    x, y, cell, _ = tile(view, pos)
    width = max(2, cell // 40)
    for inset in range(width):
        pyxel.rectb(x + inset, y + inset, cell - 2 * inset, cell - 2 * inset, RED)
    if mark:
        warning(view, pos)


def bolt(x: int, y: int, size: int, lit: bool) -> None:
    """A lightning bolt: thick and yellow when powered, thin and struck out when not."""
    points = [(65, 0), (20, 55), (50, 55), (35, 100), (85, 40), (55, 40), (65, 0)]
    scaled = [(x + px * size // 100, y + py * size // 100) for px, py in points]
    for (x1, y1), (x2, y2) in pairwise(scaled):
        pyxel.line(x1, y1, x2, y2, YELLOW if lit else LAVENDER)
        if lit:
            pyxel.line(x1 + 1, y1, x2 + 1, y2, YELLOW)
    if not lit:
        pyxel.line(x, y + size, x + size, y, LAVENDER)


def badge(
    view: View,
    pos: Position,
    text: Text,
    label: str,
    scale: int,
    char: int,
    lit: bool,
    bolt_lit: bool | None = None,
) -> None:
    """The pad letter in a box (bright when active), plus an optional power bolt."""
    x, y, cell, _ = tile(view, pos)
    pad = max(2, cell // 40)
    side = char + 2 * pad + 2
    pyxel.rect(x + pad, y + pad, side, side + 2, BLUE if lit else NAVY)
    pyxel.rectb(x + pad, y + pad, side, side + 2, WHITE if lit else LAVENDER)
    text(x + pad + 1 + pad, y + pad + 1, label, WHITE if lit else LAVENDER, scale)
    if bolt_lit is not None:
        size = side + 2
        left = x + 2 * pad + side
        pyxel.rect(left, y + pad, size, size, NAVY)
        pyxel.rectb(left, y + pad, size, size, YELLOW if bolt_lit else LAVENDER)
        inner = size - 6
        bolt(left + 3, y + pad + 3, inner, bolt_lit)


def edge_arrow(x: float, y: float, dx: float, dy: float, size: int, colour: int):
    """A filled arrowhead centred on (x, y) and pointing along the unit (dx, dy)."""
    side_x, side_y = -dy * size * 0.7, dx * size * 0.7
    points = (
        round(x + dx * size),
        round(y + dy * size),
        round(x - dx * size * 0.6 + side_x),
        round(y - dy * size * 0.6 + side_y),
        round(x - dx * size * 0.6 - side_x),
        round(y - dy * size * 0.6 - side_y),
    )
    pyxel.tri(*points, colour)
    pyxel.trib(*points, NAVY)


MARKER_COLOURS = {
    "pad": GREEN,
    "gate": AMBER,
    "elevator": WHITE,
    "echo": BLUE,
    "target": YELLOW,
}


def offscreen(view: View, rect: Rect, targets) -> None:
    """Edge arrows for the (kind, tile position) targets the view cannot see."""
    size = max(6, view[0] // 9)
    for marker in cues.offscreen_markers(view, rect, targets, size + 4):
        edge_arrow(
            marker.x,
            marker.y,
            marker.dx,
            marker.dy,
            size,
            MARKER_COLOURS[marker.kind],
        )


def links(view: View, found: tuple[DeviceLink, ...], rect: Rect | None = None) -> None:
    """Lines from each focused gate or elevator to the pad that controls it.

    With a `rect`, a link that runs out of it ends in an arrow on its edge.
    """
    cell = view[0]
    for link in found:
        x1, y1 = centre(view, link.device.position)
        x2, y2 = centre(view, link.pad_position)
        colour = BLUE if link.pad_active else GREY
        for offset in range(max(2, cell // 40)):
            pyxel.line(x1, y1 + offset, x2, y2 + offset, colour)
        pyxel.circ(x2, y2, max(3, cell // 20), colour)
        size = max(6, cell // 9)
        if rect is not None and (
            out := camera.exit_point(inset(rect, size + 4), (x1, y1), (x2, y2))
        ):
            length = max(1.0, ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5)
            edge_arrow(*out, (x2 - x1) / length, (y2 - y1) / length, size, colour)


def inset(rect: Rect, by: int) -> Rect:
    x, y, width, height = rect
    return x + by, y + by, max(1, width - 2 * by), max(1, height - 2 * by)


def countdown(
    view: View,
    pos: Position,
    text: Text,
    value: int,
    scale: int,
    char: int,
    lift: float = 0.0,
):
    """A number in the top-right corner of a timed pad: turns of power left.

    `lift` (in tiles) hops it up while the timer ticks."""
    x, y, cell, _ = tile(view, pos)
    y -= round(lift * cell)
    pad = max(2, cell // 40)
    side = char + 2 * pad + 2
    left = x + cell - side - pad
    pyxel.rect(left, y + pad, side, side + 2, NAVY)
    pyxel.rectb(left, y + pad, side, side + 2, YELLOW)
    text(left + pad + 1, y + pad + 1, str(value), YELLOW, scale)


def closing(view: View, pos: Position, text: Text, char: int, verb: str) -> None:
    """A tag along the bottom of a gate or elevator that stops next turn."""
    x, y, cell, _ = tile(view, pos)
    label = f"{verb} NEXT TURN"
    if (len(label) + 2) * char > cell:
        label = "NEXT"
    height = max(12, cell // 6)
    top = y + cell - height - 2
    pyxel.rect(x + 2, top, cell - 4, height, AMBER)
    mid = x + cell // 2
    pyxel.tri(mid - 4, top - 5, mid + 4, top - 5, mid, top, AMBER)
    text(x + (cell - len(label) * char) // 2, top + (height - 12) // 2, label, NAVY, 1)


def arrow(view: View, pos: Position, command: tuple[str, tuple[int, int]]) -> None:
    """The echo's next command: an arrowhead off its tile edge, or a ring to wait."""
    kind, (dx, dy) = command
    x, y = centre(view, pos)
    cell = view[0]
    if kind == "wait":
        pyxel.circb(x, y, cell * 2 // 5, BLUE)
        pyxel.circb(x, y, cell * 2 // 5 - 1, BLUE)
        return
    reach, wing, tip = cell * 2 // 5, max(5, cell // 10), max(6, cell // 8)
    base_x, base_y = x + dx * (reach - tip), y + dy * (reach - tip)
    tip_x, tip_y = x + dx * reach, y + dy * reach
    side_x, side_y = -dy * wing, dx * wing
    pyxel.tri(
        tip_x,
        tip_y,
        base_x + side_x,
        base_y + side_y,
        base_x - side_x,
        base_y - side_y,
        BLUE,
    )
    pyxel.trib(
        tip_x,
        tip_y,
        base_x + side_x,
        base_y + side_y,
        base_x - side_x,
        base_y - side_y,
        WHITE,
    )


def hatch(view: View, pos: Position, room: Rect) -> None:
    """Dim a tile and cross-hatch it: it would go dark. Drawing stays in `room`."""
    x, y, cell, _ = tile(view, pos)
    pyxel.dither(0.55)
    pyxel.rect(x, y, cell, cell, NAVY)
    pyxel.dither(1.0)
    left, top = max(x, room[0]), max(y, room[1])
    right, bottom = min(x + cell, room[0] + room[2]), min(y + cell, room[1] + room[3])
    pyxel.clip(left, top, max(0, right - left), max(0, bottom - top))
    gap = max(6, cell // 10)
    for offset in range(0, 2 * cell, gap):
        pyxel.line(x + offset, y, x, y + offset, GREY)
    pyxel.clip(*room)


def console_preview(
    view: View,
    found: ConsolePreview,
    devices: dict[str, Position],
    frame: int,
    still: bool,
    room: Rect,
) -> None:
    """Dim what would go dark; pulse (or outline, when still) changing devices."""
    for pos in sorted(found.dark):
        hatch(view, pos, room)
    for pos in sorted(found.lit):
        x, y, cell, _ = tile(view, pos)
        pyxel.rectb(x + 2, y + 2, cell - 4, cell - 4, GREEN)
    beat = motion.blink(frame, 0.27) == 0
    for ids, colour in ((found.losing, RED), (found.gaining, GREEN)):
        for device_id in sorted(ids):
            x, y, cell, _ = tile(view, devices[device_id])
            rings = (0, 1, 2) if still or beat else (0,)
            for inset in rings:
                pyxel.rectb(
                    x + inset, y + inset, cell - 2 * inset, cell - 2 * inset, colour
                )


def vignette(rect: tuple[int, int, int, int], level: float) -> None:
    """A red edge that fades towards the middle of `rect`; `level` is 0 to 1."""
    x, y, width, height = rect
    rings = 5
    band = max(2, height // 90)
    for ring in range(rings):
        pyxel.dither(level * (1 - ring / rings))
        inset = ring * band
        w, h = width - 2 * inset, height - 2 * inset
        pyxel.rect(x + inset, y + inset, w, band, RED)
        pyxel.rect(x + inset, y + inset + h - band, w, band, RED)
        pyxel.rect(x + inset, y + inset + band, band, h - 2 * band, RED)
        pyxel.rect(x + inset + w - band, y + inset + band, band, h - 2 * band, RED)
    pyxel.dither(1.0)


def burst(view: View, at: tuple[float, float], sparks) -> None:
    """Square sparks (offsets and sizes in tiles) around tile coordinates `at`."""
    cell, ox, oy = view
    for spark in sparks:
        size = max(2, round(spark.size * cell))
        cx = ox + (at[0] + 0.5 + spark.dx) * cell
        cy = oy + (at[1] + 0.5 + spark.dy) * cell
        pyxel.rect(cx - size / 2, cy - size / 2, size, size, spark.colour)


def fade(width: int, height: int, cover: float) -> None:
    """Cover the screen with the background colour; `cover` is 0 (none) to 1."""
    pyxel.dither(cover)
    pyxel.rect(0, 0, width, height, NAVY)
    pyxel.dither(1.0)
