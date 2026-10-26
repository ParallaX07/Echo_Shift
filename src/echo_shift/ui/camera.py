"""Pyxel-free scrolling camera: where the room's view sits over the chamber.

Everything here is presentation. The camera reads where the player is drawn and
never feeds anything back into the rules or the input. Positions are in tiles;
the view is the top-left corner of the visible window in chamber coordinates.
"""

from dataclasses import dataclass

Bounds = tuple[int, int, int, int]  # min_x, min_y, max_x, max_y (inclusive tiles)
Point = tuple[float, float]
Rect = tuple[int, int, int, int]
View = tuple[int, int, int]  # cell size, then the pixel origin of tile (0, 0)

DEAD_ZONE = 0.4  # share of the view, around its middle, where the player may roam
EASE = 0.2  # share of the remaining distance covered each frame
SETTLED = 0.01  # tiles; closer than this the camera lands exactly on its target
JUMP = 1.0  # tiles; a bigger move in one frame is a teleport and snaps the view


def centred(focus: float, size: float, low: float, high: float) -> float:
    """View start that centres `focus`, held inside [low, high]; centred if smaller."""
    if high - low <= size:
        return low - (size - (high - low)) / 2
    return min(max(focus - size / 2, low), high - size)


def follow_axis(
    current: float, focus: float, size: float, low: float, high: float
) -> float:
    """The view start the dead zone asks for: it moves only once `focus` leaves it."""
    if high - low <= size:
        return centred(focus, size, low, high)
    half = size * DEAD_ZONE / 2
    middle = current + size / 2
    if focus < middle - half:
        current = focus + half - size / 2
    elif focus > middle + half:
        current = focus - half - size / 2
    return min(max(current, low), high - size)


@dataclass
class Camera:
    """The eased view origin; call `follow` once per drawn frame."""

    x: float = 0.0
    y: float = 0.0
    key: object = None
    focus: Point | None = None

    def reset(self) -> None:
        """Forget the last view so the next frame snaps (a chamber was opened)."""
        self.key = self.focus = None

    def follow(
        self,
        focus: Point,
        size: Point,
        world: Bounds,
        key: object = None,
        reduced: bool = False,
    ) -> Point:
        """Move towards the player and return the view origin in tiles.

        `focus` is the drawn player centre, `size` the view in tiles and `world`
        the tiles that may be shown. A new `key` (window size, chamber), a first
        frame or a player who moved more than a tile at once snaps the view.
        """
        min_x, min_y, max_x, max_y = world
        lows, highs = (min_x, min_y), (max_x + 1, max_y + 1)
        last = self.focus
        snap = (
            self.key != key
            or last is None
            or abs(focus[0] - last[0]) + abs(focus[1] - last[1]) > JUMP + 1e-9
        )
        self.key, self.focus = key, focus
        current = [self.x, self.y]
        for axis in (0, 1):
            if snap:
                target = centred(focus[axis], size[axis], lows[axis], highs[axis])
                current[axis] = target
                continue
            target = follow_axis(
                current[axis], focus[axis], size[axis], lows[axis], highs[axis]
            )
            if reduced or abs(target - current[axis]) < SETTLED:
                current[axis] = target
            else:
                current[axis] += (target - current[axis]) * EASE
        self.x, self.y = current
        return self.x, self.y


def view_origin(rect: Rect, cell: int, view: Point) -> tuple[int, int]:
    """Pixel position of tile (0, 0) for a view origin in tiles, inside `rect`."""
    return rect[0] - round(view[0] * cell), rect[1] - round(view[1] * cell)


def tile_rect(view: View, x: float, y: float) -> Rect:
    """Pixel rect of the tile at (x, y) under a (cell, origin_x, origin_y) view."""
    cell, origin_x, origin_y = view
    return round(origin_x + x * cell), round(origin_y + y * cell), cell, cell


def visible(view: View, rect: Rect, x: float, y: float) -> bool:
    """Whether any part of tile (x, y) lies inside the pixel `rect`."""
    left, top, width, height = tile_rect(view, x, y)
    rx, ry, rw, rh = rect
    return left < rx + rw and left + width > rx and top < ry + rh and top + height > ry


def visible_tiles(view: View, rect: Rect, bounds: Bounds) -> Bounds | None:
    """The tiles of `bounds` that touch `rect`, as inclusive bounds (None: no tile)."""
    cell, origin_x, origin_y = view
    rx, ry, rw, rh = rect
    min_x, min_y, max_x, max_y = bounds
    found = (
        max(min_x, (rx - origin_x) // cell),
        max(min_y, (ry - origin_y) // cell),
        min(max_x, (rx + rw - 1 - origin_x) // cell),
        min(max_y, (ry + rh - 1 - origin_y) // cell),
    )
    return found if found[0] <= found[2] and found[1] <= found[3] else None


def exit_point(rect: Rect, inside: Point, outside: Point) -> Point | None:
    """Where the segment from `inside` to `outside` leaves `rect`.

    None when `outside` is within the rect too (the segment never leaves it).
    """
    x, y, width, height = rect
    dx, dy = outside[0] - inside[0], outside[1] - inside[1]
    reach = 1.0
    for delta, start, low, high in (
        (dx, inside[0], x, x + width),
        (dy, inside[1], y, y + height),
    ):
        if delta > 0:
            reach = min(reach, (high - start) / delta)
        elif delta < 0:
            reach = min(reach, (low - start) / delta)
    if not 0.0 < reach < 1.0:
        return None
    return inside[0] + dx * reach, inside[1] + dy * reach


def edge_marker(rect: Rect, target: Point, inset: int) -> tuple[Point, Point] | None:
    """Where an arrow for an off-screen `target` sits on the edge of `rect`.

    Returns the arrow's position (kept `inset` pixels inside the rect) and its
    unit direction, or None when the target is inside the rect.
    """
    x, y, width, height = rect
    inner = (
        x + inset,
        y + inset,
        max(1, width - 2 * inset),
        max(1, height - 2 * inset),
    )
    centre = (x + width / 2, y + height / 2)
    if not (x <= target[0] < x + width and y <= target[1] < y + height):
        at = exit_point(inner, centre, target)
        if at is not None:
            dx, dy = target[0] - centre[0], target[1] - centre[1]
            length = max(1e-9, (dx * dx + dy * dy) ** 0.5)
            return at, (dx / length, dy / length)
    return None
