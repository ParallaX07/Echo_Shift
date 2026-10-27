"""Pyxel-free mouse hit-testing for the room: pixels to tiles to actions."""

from echo_shift.engine.model import Position, State, TileType
from echo_shift.ui import controls, story
from echo_shift.ui.layout import Rect

View = tuple[int, int, int]  # cell size, then the pixel origin of tile (0, 0)
Bounds = tuple[int, int, int, int]  # min_x, min_y, max_x, max_y of the drawn tiles
MOVES = {delta: action_id for action_id, delta in controls.MOVE_DELTAS.items()}


def tile_at(
    view: View,
    bounds: Bounds,
    room: Rect,
    x: int,
    y: int,
    drawer_x: int | None = None,
) -> Position | None:
    """The drawn tile under pixel (x, y), or None off the room.

    `drawer_x` is the left edge of an open console drawer, which hides the tiles
    beneath it.
    """
    left, top, width, height = room
    if not (left <= x < left + width and top <= y < top + height):
        return None
    if drawer_x is not None and x >= drawer_x:
        return None
    cell, origin_x, origin_y = view
    position = Position((x - origin_x) // cell, (y - origin_y) // cell)
    min_x, min_y, max_x, max_y = bounds
    if min_x <= position.x <= max_x and min_y <= position.y <= max_y:
        return position
    return None


READ_LOG = "read_log"  # a click that reads the log terminal underfoot
POWER = "power_console"  # a click on the console tile, never a log


def click_action(
    state: State, position: Position, terminals: tuple[story.Terminal, ...] = ()
) -> str | None:
    """The action a click on `position` asks for; None when it asks for nothing.

    An adjacent tile moves, exactly like the arrow key, terminal tiles included.
    The player's own tile opens the console when it stands on one, reads the log
    terminal when it stands on one (reading is free, so it replaces waiting there;
    the bar's Wait button still waits) and waits otherwise. A console the player is
    not standing on maps to the power action, which explains why it is unavailable.
    """
    reachable = story.in_reach(state, terminals)
    if (
        reachable is not None
        and reachable.position == position
        and position == state.player
    ):
        return READ_LOG
    dx, dy = position.x - state.player.x, position.y - state.player.y
    if (dx, dy) in MOVES:
        return MOVES[(dx, dy)]
    if position == state.player:
        return POWER if position in state.chamber.consoles else "wait"
    if position in state.chamber.consoles:
        return POWER
    return None


def hover_action(
    state: State,
    position: Position,
    actions: list[controls.Action],
    terminals: tuple[story.Terminal, ...] = (),
) -> str | None:
    """The action to outline under the pointer: only ones that would do something."""
    action_id = click_action(state, position, terminals)
    if action_id is None:
        return None
    if action_id == POWER:
        # The bar's console action may read a log; the tile only opens the console.
        if state.player not in state.chamber.consoles:
            return None
        action_id = "console"
    if action_id != READ_LOG and not controls.find(actions, action_id).enabled:
        return None
    if action_id in MOVES.values() and (
        state.chamber.tile_at(position) is TileType.WALL
    ):
        return None
    return action_id
