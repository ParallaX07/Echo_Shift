"""Pyxel input, screens and rendering for the playable chambers."""

import atexit
import json
import logging
import math
import textwrap
from dataclasses import replace

import pyxel

from echo_shift.engine import lighting, power, recording
from echo_shift.engine.loader import load
from echo_shift.engine.model import Phase, Position, TileType, initial_state
from echo_shift.engine.turn import (
    Failed,
    InteractAtConsole,
    Move,
    Rejected,
    Wait,
)
from echo_shift.paths import resource_path, user_data_dir
from echo_shift.ui.atlas import Atlas
from echo_shift.ui.display import Display
from echo_shift.ui.hud import model
from echo_shift.ui.layout import Layout
from echo_shift.ui.progress import load_unlocked, save_unlocked
from echo_shift.ui.telemetry import Attempt

logger = logging.getLogger(__name__)
LEVEL_COUNT = 3
CHAMBER_NAMES = ("SAFE MOVEMENT", "POWER ALLOCATION", "RECORDING")
DARK_REMAP = (0, 1, 2, 1, 5, 5, 13, 13, 2, 5, 13, 3, 13, 13, 2, 5)
MENU_GLYPHS = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
}
CURSOR_SPRITE = (
    "A............",
    "11...........",
    "1C1..........",
    "1WC1.........",
    "1WWC1........",
    "1WWWC1.......",
    "1WWWWC1......",
    "1WWWWWC1.....",
    "1WWWWWWC1....",
    "1WWWWWWWC1...",
    "1WWWWWWWW1...",
    "1WWWW11......",
    "1WWW1.11.....",
    "1WW1...11....",
    "1W1.....11...",
    "11.......1...",
    "...1.....1...",
    "....11111....",
)
CURSOR_COLORS = {"1": 1, "A": 9, "C": 12, "W": 7}
MOVES = (
    (pyxel.KEY_W, 0, -1),
    (pyxel.KEY_UP, 0, -1),
    (pyxel.KEY_D, 1, 0),
    (pyxel.KEY_RIGHT, 1, 0),
    (pyxel.KEY_S, 0, 1),
    (pyxel.KEY_DOWN, 0, 1),
    (pyxel.KEY_A, -1, 0),
    (pyxel.KEY_LEFT, -1, 0),
)


class Game:
    def __init__(self) -> None:
        colors = json.loads(resource_path("assets", "palette.json").read_text())[
            "colors"
        ]
        pyxel.colors[:] = [int(color["hex"][1:], 16) for color in colors]
        self.display = Display()
        desktop_w, desktop_h = self.display.desktop_size()
        self.windowed_size = (
            min(1280, max(640, desktop_w - 48)),
            min(720, max(480, desktop_h - 72)),
        )
        pyxel.init(*self.windowed_size, title="Echo Shift", fps=30, display_scale=1)
        self.fullscreen = False
        self.pending_fullscreen = None
        self.layout = Layout.fit(*self.windowed_size)
        self.room_view = (self.layout.cell, self.layout.room_x, self.layout.room_y)
        self.text_cache = {}
        self.fonts = {}
        (user_data_dir() / "startup.log").write_text("Echo Shift started\n")
        self.atlas = Atlas()
        self.unlocked = load_unlocked(LEVEL_COUNT)
        self.level = 1
        self.level_cursor = 1
        self.mode = "title"
        self.mouse_visible = None
        self.last_menu_mouse = (-1, -1)
        self.mouse_active = False
        self.menu_mouse_moved = False
        self.modal = None
        self.tutorial = []
        self.hints = []
        self.hint_index = 0
        self.seen_hints = set()
        self.muted = False
        self.state = initial_state(load(resource_path("levels", "chamber_01.json")))
        self.paused = False
        self.console = False
        self.selection = 0
        self.pending = self.state.powered_circuits
        self.message = "E POWER  ENTER RECORD"
        self.message_frames = 120
        self.flash = 0
        self.attempt = None
        atexit.register(self.finish_attempt)

    def finish_attempt(self, completed: bool = False) -> None:
        if self.attempt is not None:
            self.attempt.finish(completed)
            self.attempt = None

    def open_level(self, number: int) -> None:
        self.finish_attempt()
        path = resource_path("levels", f"chamber_{number:02}.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.level = number
        self.attempt = Attempt(number)
        self.state = initial_state(load(path))
        self.tutorial = data["tutorial"]
        self.hints = data["hints"]
        self.hint_index = 0
        self.seen_hints = set()
        self.mode = "game"
        self.sync_mouse()
        self.modal = "tutorial"
        self.paused = False
        self.console = False
        self.pending = self.state.powered_circuits
        self.notice("E POWER  ENTER RECORD")

    def unlock_next(self) -> None:
        unlocked = min(LEVEL_COUNT, self.level + 1)
        if unlocked > self.unlocked:
            save_unlocked(unlocked)
            self.unlocked = unlocked

    def show_hint(self) -> None:
        if self.hint_index < len(self.hints):
            self.attempt.hints += 1
            self.seen_hints.add(self.hint_index)
            self.hint_index += 1
            self.modal = "hint"
        else:
            self.modal = None
            self.notice("NO MORE HINTS")

    def notice(self, message: str, error: bool = False) -> None:
        self.message = message.upper()
        self.message_frames = 120
        self.flash = 12 if error else 0

    def act(self, action: Move | Wait | InteractAtConsole) -> None:
        result = recording.act(self.state, action)
        self.state = result.state
        outcome = (
            "rejected"
            if isinstance(result, Rejected)
            else "failed"
            if isinstance(result, Failed)
            else "accepted"
        )
        details = (
            f"action={action!r} outcome={outcome} phase={self.state.phase.value} "
            f"turn={self.state.turns} player=({self.state.player.x},{self.state.player.y}) "
            f"echo={self.state.echo_position} powered={sorted(self.state.powered_circuits)} "
            f"gates_open={sorted(self.state.gates_open)} "
            f"elevators_running={sorted(self.state.elevators_running)}"
        )
        if isinstance(result, Rejected):
            logger.warning("%s reason=%s", details, result.reason)
            self.notice(result.reason, True)
        elif isinstance(result, Failed):
            self.attempt.resets += 1
            logger.warning("%s reason=%s", details, result.reason)
            self.notice(f"FAILED: {result.reason}  R RETRY", True)
        else:
            logger.info("%s", details)
            if result.succeeded:
                self.finish_attempt(completed=True)
                self.unlock_next()
                self.modal = "result"
                self.notice("ELEVATOR REACHED!")

    def update(self) -> None:
        self.sync_display()
        self.sync_mouse()
        if pyxel.btnp(pyxel.KEY_F11):
            self.toggle_fullscreen()
            return
        if (
            any(
                pyxel.btn(key)
                for key in (pyxel.KEY_ALT, pyxel.KEY_LALT, pyxel.KEY_RALT)
            )
            if hasattr(pyxel, "btn")
            else False
        ):
            return
        self.message_frames = max(0, self.message_frames - 1)
        self.flash = max(0, self.flash - 1)
        if pyxel.btnp(pyxel.KEY_M):
            self.muted = not self.muted
        if self.mode in ("title", "levels"):
            pointer = self.menu_mouse_position()
            self.menu_mouse_moved = pointer != self.last_menu_mouse
            if self.menu_mouse_moved:
                self.mouse_active = True
            self.last_menu_mouse = pointer
        if self.mode == "title":
            if (
                pyxel.btnp(pyxel.KEY_RETURN)
                or pyxel.btnp(pyxel.KEY_SPACE)
                or self.menu_click(self.layout.start_button())
            ):
                self.mode = "levels"
            return
        if self.mode == "levels":
            hovered = self.hovered_chamber()
            if self.menu_mouse_moved and hovered is not None:
                self.level_cursor = hovered
            if pyxel.btnp(pyxel.KEY_ESCAPE):
                self.mode = "title"
            elif pyxel.btnp(pyxel.KEY_UP) or pyxel.btnp(pyxel.KEY_W):
                self.level_cursor = max(1, self.level_cursor - 1)
                self.mouse_active = False
            elif pyxel.btnp(pyxel.KEY_DOWN) or pyxel.btnp(pyxel.KEY_S):
                self.level_cursor = min(LEVEL_COUNT, self.level_cursor + 1)
                self.mouse_active = False
            elif pyxel.btnp(pyxel.KEY_LEFT) or pyxel.btnp(pyxel.KEY_A):
                self.level_cursor = max(1, self.level_cursor - 1)
                self.mouse_active = False
            elif pyxel.btnp(pyxel.KEY_RIGHT) or pyxel.btnp(pyxel.KEY_D):
                self.level_cursor = min(LEVEL_COUNT, self.level_cursor + 1)
                self.mouse_active = False
            elif hovered is not None and self.menu_click(
                self.layout.chamber_cards(LEVEL_COUNT)[hovered - 1]
            ):
                if hovered <= self.unlocked:
                    self.open_level(hovered)
            elif pyxel.btnp(pyxel.KEY_RETURN) and self.level_cursor <= self.unlocked:
                self.open_level(self.level_cursor)
            return
        if self.modal == "result":
            if pyxel.btnp(pyxel.KEY_RETURN):
                if self.level < LEVEL_COUNT:
                    self.open_level(self.level + 1)
                else:
                    self.mode = "levels"
                    self.modal = None
            elif pyxel.btnp(pyxel.KEY_L) or pyxel.btnp(pyxel.KEY_ESCAPE):
                self.mode = "levels"
                self.level_cursor = self.level
                self.modal = None
            elif pyxel.btnp(pyxel.KEY_C):
                self.open_level(self.level)
            return
        if self.modal:
            if pyxel.btnp(pyxel.KEY_L):
                self.finish_attempt()
                self.mode = "levels"
                self.level_cursor = self.level
                self.modal = None
            elif pyxel.btnp(pyxel.KEY_H):
                self.show_hint()
            elif (
                pyxel.btnp(pyxel.KEY_RETURN)
                or pyxel.btnp(pyxel.KEY_ESCAPE)
                or (self.modal == "tutorial" and pyxel.btnp(pyxel.KEY_T))
            ):
                self.modal = None
            return
        if pyxel.btnp(pyxel.KEY_L):
            self.finish_attempt()
            self.mode = "levels"
            self.level_cursor = self.level
            self.paused = False
            self.console = False
            return
        if pyxel.btnp(pyxel.KEY_P):
            self.paused = not self.paused
        if self.paused:
            if pyxel.btnp(pyxel.KEY_C):
                self.attempt.resets += 1
                self.state = recording.clear(self.state)
                self.paused = False
                self.notice("CHAMBER CLEARED")
            return
        if self.console:
            self.console_input()
            return
        if pyxel.btnp(pyxel.KEY_T):
            self.modal = "tutorial"
        elif pyxel.btnp(pyxel.KEY_H):
            self.show_hint()
        elif pyxel.btnp(pyxel.KEY_C):
            self.attempt.resets += 1
            self.state = recording.clear(self.state)
            self.notice("CHAMBER CLEARED")
        elif pyxel.btnp(pyxel.KEY_R):
            retried = recording.retry(self.state)
            if retried is not self.state:
                self.attempt.resets += 1
            self.notice(
                "RETRY FROM LAUNCH" if retried is not self.state else "LAUNCH FIRST",
                retried is self.state,
            )
            self.state = retried
        elif pyxel.btnp(pyxel.KEY_E):
            if self.state.player in self.state.chamber.consoles:
                self.console = True
                self.pending = self.state.powered_circuits
                self.selection = 0
            else:
                self.notice("STAND ON THE HUB CONSOLE", True)
        elif pyxel.btnp(pyxel.KEY_RETURN):
            before = self.state.phase
            self.state = recording.enter(self.state)
            if self.state.phase is not before:
                self.notice(
                    "RECORDING: MOVE OR SPACE, ENTER TO COMMIT"
                    if self.state.phase is Phase.RECORDING
                    else "COMMITTED: E CHANGE POWER, Q LAUNCH"
                )
        elif pyxel.btnp(pyxel.KEY_Q):
            before = self.state
            self.state = recording.launch(self.state)
            self.notice(
                "ECHO LAUNCHED: REACH THE ELEVATOR"
                if self.state is not before
                else "COMMIT A RECORDING AT THE HUB FIRST",
                self.state is before,
            )
        elif pyxel.btnp(pyxel.KEY_SPACE):
            self.act(Wait())
        else:
            for key, dx, dy in MOVES:
                if pyxel.btnp(key, hold=8, repeat=5):
                    self.act(Move(dx, dy))
                    break

    def console_input(self) -> None:
        circuits = self.state.chamber.circuits
        if pyxel.btnp(pyxel.KEY_E) or pyxel.btnp(pyxel.KEY_ESCAPE):
            self.console = False
        elif pyxel.btnp(pyxel.KEY_UP) or pyxel.btnp(pyxel.KEY_W):
            self.selection = (self.selection - 1) % len(circuits)
        elif pyxel.btnp(pyxel.KEY_DOWN) or pyxel.btnp(pyxel.KEY_S):
            self.selection = (self.selection + 1) % len(circuits)
        elif pyxel.btnp(pyxel.KEY_SPACE):
            name = circuits[self.selection].id
            self.pending = frozenset(self.pending ^ {name})
        elif pyxel.btnp(pyxel.KEY_RETURN):
            if not power.apply(self.state.chamber, self.pending).ok:
                self.attempt.unsafe_power_choices += 1
                self.notice("OVER BUDGET - REMOVE A CIRCUIT", True)
            elif self.pending == self.state.powered_circuits:
                self.console = False
            else:
                self.act(InteractAtConsole(self.pending))
                self.console = False

    def sync_mouse(self) -> None:
        visible = False
        if visible != self.mouse_visible and hasattr(pyxel, "mouse"):
            pyxel.mouse(visible)
            self.mouse_visible = visible

    def menu_mouse_position(self) -> tuple[int, int]:
        return getattr(pyxel, "mouse_x", -1), getattr(pyxel, "mouse_y", -1)

    def menu_hit(self, rect: tuple[int, int, int, int]) -> bool:
        mx, my = self.menu_mouse_position()
        x, y, width, height = rect
        return x <= mx < x + width and y <= my < y + height

    def menu_click(self, rect: tuple[int, int, int, int]) -> bool:
        return (
            self.menu_hit(rect)
            and hasattr(pyxel, "MOUSE_BUTTON_LEFT")
            and pyxel.btnp(pyxel.MOUSE_BUTTON_LEFT)
        )

    def hovered_chamber(self) -> int | None:
        for number, rect in enumerate(self.layout.chamber_cards(LEVEL_COUNT), 1):
            if self.menu_hit(rect):
                return number
        return None

    def sync_display(self) -> None:
        measured = self.display.window()
        if measured is None:
            return
        width, height, fullscreen = measured
        if width <= 0 or height <= 0:
            return
        if self.pending_fullscreen is not None:
            if fullscreen != self.pending_fullscreen:
                return
            self.pending_fullscreen = None
        if fullscreen != self.fullscreen:
            self.fullscreen = fullscreen
            if not fullscreen:
                width, height = self.windowed_size
                pyxel.resize(width, height)
        if not fullscreen and (width, height) != self.windowed_size:
            self.windowed_size = (width, height)
        if (pyxel.width, pyxel.height) != (width, height):
            pyxel.resize(width, height)
        self.layout = Layout.fit(width, height)

    def toggle_fullscreen(self) -> None:
        if not self.fullscreen:
            self.windowed_size = (self.layout.width, self.layout.height)
        self.fullscreen = not self.fullscreen
        self.pending_fullscreen = self.fullscreen
        pyxel.fullscreen(self.fullscreen)
        if not self.fullscreen:
            pyxel.resize(*self.windowed_size)
            self.layout = Layout.fit(*self.windowed_size)

    def text(
        self, x: int, y: int, value: str, color: int = 7, scale: int | None = None
    ) -> None:
        scale = scale or self.layout.text_scale
        font = self.ui_font(scale)
        if font is not None:
            pyxel.text(x, y, value, color, font)
            return
        if not hasattr(pyxel, "Image"):
            pyxel.text(x, y, value, color)
            return
        key = (value, color)
        if key not in self.text_cache:
            image = pyxel.Image(max(1, len(value) * 4), 7)
            image.cls(0)
            image.text(0, 0, value, color)
            self.text_cache[key] = image
        image = self.text_cache[key]
        pyxel.blt(
            x + image.width * (scale - 1) / 2,
            y + image.height * (scale - 1) / 2,
            image,
            0,
            0,
            image.width,
            image.height,
            0,
            scale=scale,
        )

    def ui_font(self, scale: int):
        if self.mode != "game" or not hasattr(pyxel, "Font"):
            return None
        if scale not in self.fonts:
            path = resource_path("assets", "fonts", "DejaVuSansMono.ttf")
            self.fonts[scale] = pyxel.Font(str(path), max(12, scale * 6 + 4))
        return self.fonts[scale]

    def char_width(self, scale: int) -> int:
        font = self.ui_font(scale)
        return font.text_width("M") if font is not None else 4 * scale

    def wrapped(
        self,
        x: int,
        y: int,
        value: str,
        width: int,
        color: int = 7,
        scale: int | None = None,
    ) -> int:
        scale = scale or self.layout.text_scale
        chars = max(8, width // self.char_width(scale))
        for line in textwrap.wrap(
            value, width=chars, break_long_words=True, break_on_hyphens=False
        ):
            self.text(x, y, line, color, scale)
            y += 9 * scale
        return y

    def centered(
        self, y: int, value: str, color: int = 7, scale: int | None = None
    ) -> None:
        scale = scale or self.layout.text_scale
        self.text(
            (self.layout.width - len(value) * 4 * scale) // 2, y, value, color, scale
        )

    def sprite(self, name: str, pos: Position) -> None:
        cell, x, y = self.room_view
        self.atlas.draw(
            name,
            x + pos.x * cell,
            y + pos.y * cell,
            cell,
        )

    def draw_room(self) -> None:
        state = self.state
        layout = self.layout
        lit = lighting.lit_tiles(state)
        pads = {pad.position: pad for pad in state.chamber.pads}
        devices = {device.position: device for device in state.chamber.devices}
        route = {
            Position(x, y)
            for y, row in enumerate(state.chamber.tiles)
            for x, tile in enumerate(row)
            if tile is not TileType.WALL
        }
        min_x = max(0, min(pos.x for pos in route) - 1)
        max_x = min(len(state.chamber.tiles[0]) - 1, max(pos.x for pos in route) + 1)
        min_y = max(0, min(pos.y for pos in route) - 1)
        max_y = min(len(state.chamber.tiles) - 1, max(pos.y for pos in route) + 1)
        columns, rows = max_x - min_x + 1, max_y - min_y + 1
        cell = max(
            1,
            min(
                layout.room_w // (columns + 1),
                (layout.room_h - 2 * layout.cell) // rows,
            ),
        )
        origin_x = layout.room_x + (layout.room_w - columns * cell) // 2 - min_x * cell
        origin_y = layout.room_y + (layout.room_h - rows * cell) // 2 - min_y * cell
        self.room_view = cell, origin_x, origin_y
        for y, row in enumerate(state.chamber.tiles):
            for x, tile in enumerate(row):
                if not (min_x <= x <= max_x and min_y <= y <= max_y):
                    continue
                pos = Position(x, y)
                dark = pos not in lit and tile is not TileType.WALL
                distant_wall = tile is TileType.WALL and not any(
                    abs(pos.x - floor.x) + abs(pos.y - floor.y) <= 1 for floor in route
                )
                if distant_wall:
                    pyxel.rect(
                        origin_x + x * cell,
                        origin_y + y * cell,
                        cell,
                        cell,
                        1,
                    )
                    continue
                remap = DARK_REMAP if dark else None
                if remap:
                    for source, target in enumerate(remap):
                        pyxel.pal(source, target)
                base = (
                    "wall"
                    if tile is TileType.WALL
                    else "floor_hub"
                    if pos in state.chamber.hub
                    else "floor_lit"
                )
                self.sprite(base, pos)
                if pos in pads:
                    pad = pads[pos]
                    prefix = "pad_timed" if pad.timer_length else "pad"
                    self.sprite(
                        prefix + ("_on" if pad.id in state.pad_active else "_off"), pos
                    )
                elif pos in devices:
                    device = devices[pos]
                    if device.kind is TileType.GATE:
                        self.sprite(
                            "gate_open"
                            if device.id in state.gates_open
                            else "gate_closed",
                            pos,
                        )
                    else:
                        self.sprite(
                            "elevator_on"
                            if device.id in state.elevators_running
                            else "elevator_off",
                            pos,
                        )
                elif pos in state.chamber.consoles:
                    self.sprite("console", pos)
                if remap:
                    pyxel.pal()
                if pos in pads or pos in devices:
                    self.text(
                        origin_x + x * cell + 4,
                        origin_y + y * cell + 4,
                        "A",
                        7,
                        max(1, round(cell / 48) - 1),
                    )
        margin = max(12, layout.cell // 3)
        frame_top = layout.room_y + margin
        frame_bottom = layout.room_y + layout.room_h - margin
        pyxel.rect(
            margin,
            frame_top + layout.cell,
            1,
            frame_bottom - frame_top - layout.cell,
            5,
        )
        pyxel.rect(layout.room_w - margin, frame_top, 1, frame_bottom - frame_top, 5)
        pyxel.rect(margin, frame_bottom, layout.room_w - 2 * margin, 1, 5)
        pyxel.rect(
            layout.cell * 3, frame_top, layout.room_w - margin - layout.cell * 3, 1, 5
        )
        pyxel.rect(layout.cell * 3, frame_top, layout.cell * 2, 3, 12)
        pyxel.rect(
            layout.room_w - margin - layout.cell * 2,
            layout.room_y + layout.room_h - margin - 3,
            layout.cell * 2,
            3,
            9,
        )
        left = origin_x + min(pos.x for pos in route) * cell
        right = origin_x + (max(pos.x for pos in route) + 1) * cell
        top = origin_y + min(pos.y for pos in route) * cell
        bottom = origin_y + (max(pos.y for pos in route) + 1) * cell
        rail = max(2, cell // 32)
        pyxel.rect(left, top - rail * 3, right - left, rail, 5)
        pyxel.rect(left, bottom + rail * 2, right - left, rail, 5)
        for edge in (left, right - rail * 2):
            pyxel.rect(edge, top - rail * 5, rail * 2, rail * 5, 12)
            pyxel.rect(edge, bottom, rail * 2, rail * 5, 9)
        label_scale = max(2, layout.text_scale + 1)
        label_y = layout.room_y + layout.cell // 4
        self.text(layout.cell // 2, label_y, f"{self.level:02}", 9, label_scale + 3)
        self.text(
            layout.cell // 2,
            label_y + (label_scale + 3) * 9,
            CHAMBER_NAMES[self.level - 1],
            7,
            label_scale,
        )
        pyxel.rect(
            layout.cell // 2,
            label_y + (label_scale + 3) * 17,
            layout.cell * 2,
            rail,
            12,
        )
        frame = getattr(pyxel, "frame_count", 0) // 12 % 2
        if state.echo_position is not None:
            self.sprite(f"echo_idle_{frame}", state.echo_position)
        self.sprite(f"player_idle_{frame}", state.player)
        if self.flash and self.flash % 4 < 2:
            pyxel.rectb(layout.room_x, layout.room_y, layout.room_w, layout.room_h, 8)

    def draw_hud(self) -> None:
        layout = self.layout
        info = model(self.state)
        pyxel.rect(layout.panel_x, 0, layout.panel_w, layout.panel_h, 1)
        pyxel.rect(layout.panel_x, 0, max(2, layout.cell // 24), layout.panel_h, 12)
        x, _, width = layout.panel_content()
        unit = layout.cell / 96
        at = lambda value: round(value * unit)
        small = 1 if width < 240 else 3 if layout.cell >= 90 else 2
        title = max(2, small + 1)

        def card(start: int, end: int, accent: int) -> None:
            pyxel.rectb(x, at(start), width, at(end - start), 5)
            pyxel.rect(x, at(start), min(width // 4, at(54)), max(2, at(3)), accent)

        self.text(
            x,
            at(22),
            f"{self.level:02}  {CHAMBER_NAMES[self.level - 1]}",
            7,
            min(3, title),
        )
        pyxel.rect(x, at(61), width, max(1, at(2)), 5)

        card(78, 245, 10)
        self.text(x + at(14), at(91), "POWER", 10, small)
        self.text(x + at(14), at(120), f"{info.load} / {info.capacity} UNITS", 7, title)
        pyxel.rectb(x + at(14), at(151), width - at(28), max(8, at(13)), 6)
        pyxel.rect(
            x + at(16),
            at(153),
            round((width - at(32)) * info.load / max(1, info.capacity)),
            max(4, at(9)),
            11,
        )
        self.text(x + at(14), at(176), "CIRCUITS", 6, min(2, small))
        for index, (name, on) in enumerate(info.circuits):
            cy = at(193 + index * 18)
            pyxel.rect(
                x + at(14), cy + at(2), max(4, at(7)), max(4, at(7)), 11 if on else 8
            )
            self.text(x + at(27), cy, name.upper().replace("-", " "), 7, min(2, small))
        card(257, 350, 11 if info.safe else 8)
        self.text(
            x + at(14),
            at(270),
            "SAFE" if info.safe else "DARK",
            11 if info.safe else 8,
            title,
        )
        hints = f"HINTS {len(self.seen_hints)}/{len(self.hints)}"
        self.text(
            x + width - at(14) - len(hints) * self.char_width(2),
            at(276),
            hints,
            14,
            2,
        )
        feedback = (
            self.message if self.message_frames else self.state.phase.value.upper()
        )
        self.wrapped(
            x + at(14),
            at(305),
            feedback,
            width - at(28),
            8 if self.flash else 7,
            min(2, small),
        )

        card(365, 540, 9)
        self.text(x + at(14), at(376), "CONTROLS", 10, min(2, small))
        for row, line in enumerate(
            (
                "WASD / ARROWS  MOVE",
                "SPACE WAIT   E POWER",
                "ENTER RECORD  Q LAUNCH",
                "R RETRY  C CLEAR",
                "T HELP  H HINT  P PAUSE",
                "L LEVELS  F11 FULLSCREEN",
            )
        ):
            self.text(x + at(14), at(397 + row * 24), line, 7 if row < 3 else 6, small)
        self.text(x, at(550), "ECHO TIMELINE", 12, small)
        count = self.state.chamber.max_turns
        recorded = f"{len(self.state.recording)}/{count}"
        self.text(
            x + width - at(14) - len(recorded) * self.char_width(small),
            at(550),
            recorded,
            7,
            small,
        )
        for index, ((kind, current, direction), (sx, sy, slot)) in enumerate(
            zip(info.timeline[:count], layout.timeline_slots(count))
        ):
            pyxel.rectb(sx, sy, slot, slot, 12 if current else 5)
            if kind != "empty":
                self.atlas.draw("slot_" + kind, sx, sy, slot)
            else:
                self.text(sx + at(7), sy + at(7), f"{index + 1:02}", 13, small)
            if direction:
                self.text(
                    sx + slot - self.char_width(small) - at(4),
                    sy + slot - 8 * layout.text_scale,
                    direction,
                    7,
                )
            if current:
                pyxel.rectb(sx, sy, slot, slot, 12)
        if self.muted:
            self.text(
                x + width - 5 * self.char_width(small), at(24), "MUTED", 13, small
            )

    def draw_panel(
        self, title: str, lines: list[str], footer: str, numbered: bool = False
    ) -> None:
        _, _, width, max_height = self.layout.overlay()
        pad = max(18, self.layout.cell // 4)
        scale = self.layout.text_scale + int(numbered)
        title_scale = max(2, scale + 1)
        inset = 40 * scale // 2 if numbered else 0
        line_width = width - 2 * pad - inset
        line_count = sum(
            max(
                1,
                len(
                    textwrap.wrap(
                        line, width=max(8, line_width // self.char_width(scale))
                    )
                ),
            )
            for line in lines
        )
        body_height = line_count * 9 * scale + len(lines) * 12 * scale
        footer_lines = max(
            1,
            len(
                textwrap.wrap(
                    footer,
                    width=max(
                        8,
                        (width - 2 * pad) // self.char_width(self.layout.text_scale),
                    ),
                )
            ),
        )
        footer_height = footer_lines * 9 * self.layout.text_scale
        height = min(
            max_height,
            2 * pad + 12 * title_scale + body_height + footer_height + 24,
        )
        x = (self.layout.width - width) // 2
        y = (self.layout.height - height) // 2
        pyxel.rect(x + 6, y + 6, width, height, 5)
        pyxel.rect(x, y, width, height, 1)
        pyxel.rectb(x, y, width, height, 12)
        pyxel.rect(x, y, min(width // 5, pad * 4), max(3, self.layout.text_scale), 9)
        self.text(x + pad, y + pad, title, 10, title_scale)
        cursor = y + pad + 12 * title_scale
        pyxel.rect(x + pad, cursor, width - 2 * pad, max(1, self.layout.text_scale), 5)
        cursor += 14
        for index, line in enumerate(lines, 1):
            if numbered:
                self.text(x + pad, cursor, f"{index:02}", 9, scale)
            cursor = (
                self.wrapped(x + pad + inset, cursor, line, line_width, 7, scale)
                + 12 * scale
            )
        footer_y = y + height - pad - footer_height
        pyxel.rect(
            x + pad, footer_y - 11, width - 2 * pad, max(1, self.layout.text_scale), 5
        )
        self.wrapped(
            x + pad,
            footer_y,
            footer,
            width - 2 * pad,
            12,
        )

    def draw_console(self) -> None:
        circuits = self.state.chamber.circuits
        configured = power.apply(self.state.chamber, self.pending)
        pending_load = sum(c.load for c in circuits if c.id in self.pending)
        before = lighting.lit_tiles(self.state)
        after = lighting.lit_tiles(replace(self.state, powered_circuits=self.pending))
        dark = sorted(
            zone.id
            for zone in self.state.chamber.zones
            if any(tile in before and tile not in after for tile in zone.tiles)
        )
        lines = ["UP/DOWN SELECT  SPACE TOGGLE  ENTER APPLY  E EXIT"]
        lines += [
            f"{'>' if index == self.selection else ' '} [{'X' if circuit.id in self.pending else ' '}] {circuit.id.upper()}  {circuit.load} UNITS"
            for index, circuit in enumerate(circuits)
        ]
        lines += [f"PENDING LOAD {pending_load}/{self.state.chamber.capacity}"]
        if not configured.ok:
            lines.append("OVER BUDGET - CANNOT APPLY")
        lines.append("WILL GO DARK: " + (", ".join(dark).upper() if dark else "NONE"))
        self.draw_panel(
            "POWER CONSOLE", lines, "ENTER RECORD  Q LAUNCH  T HELP  H HINT"
        )

    def draw_menu_background(self) -> None:
        width, height = self.layout.width, self.layout.height
        tile = max(24, self.layout.menu_rect(0, 0, 96, 96)[2])
        for y in range(0, height, tile):
            for x in range(0, width, tile):
                self.atlas.draw("menu_background", x, y, tile)
        x, y, panel_w, panel_h = self.layout.menu_rect(72, 40, 1136, 640)
        pyxel.rect(x, y, panel_w, panel_h, 1)
        pyxel.rectb(x, y, panel_w, panel_h, 6)
        px, py, pw, _ = self.layout.menu_rect(95, 58, 1090, 2)
        pyxel.rect(px, py, pw, max(1, self.layout.menu_rect(0, 0, 0, 2)[3]), 5)
        frame = getattr(pyxel, "frame_count", 0)
        pulse_x = px + (frame * 3) % max(1, pw - 65)
        pyxel.rect(pulse_x, py, min(65, pw), max(1, self.layout.text_scale), 12)
        left, top, rail_w, rail_h = self.layout.menu_rect(94, 652, 1092, 3)
        pyxel.rect(left, top, rail_w, max(1, rail_h), 5)
        pyxel.rect(
            left + rail_w - min(95, rail_w), top, min(95, rail_w), max(1, rail_h), 9
        )
        for side in (110, 1160):
            sx, sy, sw, sh = self.layout.menu_rect(side, 104, 3, 500)
            pyxel.rect(sx, sy, max(1, sw), sh, 5)
            step = self.layout.menu_rect(0, 0, 0, 85)[3]
            tick = sy + (frame * 2) % max(1, sh - step)
            pyxel.rect(
                sx, tick, max(1, sw), max(4, step // 2), 12 if side == 1160 else 9
            )

    def draw_menu_letters(self, value: str, y: int, pixel: int, color: int) -> None:
        width = (len(value) * 6 - 1) * pixel
        x = (self.layout.width - width) // 2
        for shift, ink in ((max(1, pixel // 2), 5), (0, color)):
            for index, letter in enumerate(value):
                for row, bits in enumerate(MENU_GLYPHS.get(letter, ())):
                    for column, bit in enumerate(bits):
                        if bit == "1":
                            pyxel.rect(
                                x + (index * 6 + column) * pixel + shift,
                                y + row * pixel + shift,
                                pixel,
                                pixel,
                                ink,
                            )

    def draw_cursor(self) -> None:
        x, y = self.menu_mouse_position()
        if not (0 <= x < self.layout.width and 0 <= y < self.layout.height):
            return
        for row, pixels in enumerate(CURSOR_SPRITE):
            for column, pixel in enumerate(pixels):
                if pixel != ".":
                    pyxel.rect(x + column, y + row, 1, 1, CURSOR_COLORS[pixel])

    def draw_title(self) -> None:
        self.draw_menu_background()
        logo_x, logo_y, logo_size, _ = self.layout.menu_rect(566, 78, 148, 148)
        self.atlas.draw("menu_emblem", logo_x, logo_y, logo_size)
        title_y = self.layout.menu_rect(0, 244, 0, 0)[1]
        pixel = max(2, self.layout.menu_rect(0, 0, 8, 0)[2])
        self.draw_menu_letters("ECHO SHIFT", title_y, pixel, 7)
        subtitle_y = self.layout.menu_rect(0, 321, 0, 0)[1]
        self.centered(subtitle_y, "BEND THE LIGHT. OUTRUN YOUR ECHO.", 12)
        frame = getattr(pyxel, "frame_count", 0)
        bob = round(5 * math.sin(frame * math.tau / 90))
        sprite_size = self.layout.menu_rect(0, 0, 194, 0)[2]
        player_x, player_y, _, _ = self.layout.menu_rect(414, 351, 0, 0)
        echo_x, echo_y, _, _ = self.layout.menu_rect(677, 351, 0, 0)
        self.atlas.draw(
            f"player_idle_{frame // 15 % 2}", player_x, player_y + bob, sprite_size
        )
        self.atlas.draw(
            f"echo_idle_{frame // 15 % 2}", echo_x, echo_y - bob, sprite_size
        )
        button = self.layout.start_button()
        x, y, width, height = button
        hovered = self.mouse_active and self.menu_hit(button)
        pulse = frame // 18 % 2 == 0
        pyxel.rect(x, y, width, height, 5 if hovered else 1)
        pyxel.rectb(x, y, width, height, 10 if hovered or pulse else 9)
        accent = max(2, self.layout.text_scale)
        pyxel.rect(x + accent, y + accent, max(12, width // 5), accent, 12)
        label = "ENTER / CLICK" if width < 250 else "CLICK OR ENTER TO START"
        text_scale = max(1, self.layout.text_scale + 1)
        self.text(
            x + (width - len(label) * 4 * text_scale) // 2,
            y + (height - 7 * text_scale) // 2,
            label,
            10,
            text_scale,
        )
        footer_y = self.layout.menu_rect(0, 631, 0, 0)[1]
        self.centered(footer_y, "M: MUTE / UNMUTE     F11: FULLSCREEN", 13)
        self.draw_cursor()

    def draw_levels(self) -> None:
        self.draw_menu_background()
        logo_x, logo_y, logo_size, _ = self.layout.menu_rect(195, 89, 80, 80)
        self.atlas.draw("menu_emblem", logo_x, logo_y, logo_size)
        header_y = self.layout.menu_rect(0, 104, 0, 0)[1]
        pixel = max(2, self.layout.menu_rect(0, 0, 5, 0)[2])
        self.draw_menu_letters("SELECT CHAMBER", header_y, pixel, 12)
        subtitle_y = self.layout.menu_rect(0, 169, 0, 0)[1]
        self.centered(subtitle_y, "RESTORE THE CIRCUIT. FIND THE EXIT.", 7)
        frame = getattr(pyxel, "frame_count", 0)
        cards = self.layout.chamber_cards(LEVEL_COUNT)
        art = ("player_idle_0", "console", "echo_idle_0")
        for number, (x, y, width, height) in enumerate(cards, 1):
            unlocked = number <= self.unlocked
            selected = number == self.level_cursor
            hovered = self.mouse_active and self.menu_hit((x, y, width, height))
            color = 10 if selected and frame // 18 % 2 == 0 else 12 if selected else 6
            if not unlocked:
                color = 5 if not selected else 13
            pyxel.rect(x, y, width, height, 1)
            pyxel.rectb(x, y, width, height, color)
            inset = max(3, self.layout.text_scale * 2)
            pyxel.rectb(x + inset, y + inset, width - 2 * inset, height - 2 * inset, 5)
            if selected or hovered:
                bar = max(15, width // 5)
                travel = max(1, width - 2 * inset - bar)
                pyxel.rect(x + inset + frame * 2 % travel, y + inset, bar, inset, color)
            number_scale = max(2, self.layout.text_scale + 4)
            self.text(
                x + inset * 3,
                y + inset * 4,
                f"{number:02}",
                9 if unlocked else 13,
                number_scale,
            )
            signal_y = y + height // 2
            pyxel.rect(
                x + inset * 3,
                signal_y,
                width - inset * 6,
                max(1, self.layout.text_scale),
                5,
            )
            pyxel.rect(x + inset * 3, signal_y - inset, inset, inset * 2, color)
            pyxel.rect(
                x + width - inset * 4,
                signal_y - inset,
                inset,
                inset * 2,
                color,
            )
            if unlocked:
                size = min(width * 3 // 5, height * 11 // 20)
                self.atlas.draw(
                    art[(number - 1) % len(art)],
                    x + (width - size) // 2,
                    y + height // 6,
                    size,
                )
            else:
                lock_width = min(width // 4, height // 4)
                lock_x = x + (width - lock_width) // 2
                lock_y = y + height // 3
                pyxel.rectb(
                    lock_x + lock_width // 5,
                    lock_y,
                    lock_width * 3 // 5,
                    lock_width // 2,
                    13,
                )
                pyxel.rectb(
                    lock_x,
                    lock_y + lock_width // 3,
                    lock_width,
                    lock_width * 2 // 3,
                    13,
                )
                pyxel.rect(
                    lock_x + lock_width // 2,
                    lock_y + lock_width * 2 // 3,
                    max(1, inset // 2),
                    inset,
                    13,
                )
            divider_y = y + height * 2 // 3
            pyxel.rect(
                x + inset * 3,
                divider_y,
                width - inset * 6,
                max(1, self.layout.text_scale),
                12 if unlocked else 5,
            )
            name = (
                CHAMBER_NAMES[number - 1]
                if number <= len(CHAMBER_NAMES)
                else f"CHAMBER {number}"
            )
            label_scale = max(1, self.layout.text_scale + 1)
            self.text(
                x + inset * 3,
                divider_y + inset * 3,
                name,
                7 if unlocked else 13,
                label_scale,
            )
            self.text(
                x + inset * 3,
                y + height - inset * 5,
                "READY  >" if unlocked else "LOCKED",
                10 if unlocked else 5,
            )
        footer_y = self.layout.menu_rect(0, 621, 0, 0)[1]
        self.centered(
            footer_y,
            "ARROWS / WASD: SELECT     ENTER / CLICK: PLAY     ESC: TITLE     F11: FULLSCREEN",
        )
        self.draw_cursor()

    def draw_modal(self) -> None:
        if self.modal == "tutorial":
            self.draw_panel(
                f"CHAMBER {self.level:02}  /  FIELD GUIDE",
                self.tutorial,
                "ENTER/T: CLOSE  H: HINT  L: LEVEL SELECT",
                numbered=True,
            )
        elif self.modal == "hint":
            self.draw_panel(
                f"HINT {self.hint_index}/{len(self.hints)}  USED {len(self.seen_hints)}",
                [self.hints[self.hint_index - 1]],
                "ENTER: CLOSE  H: NEXT HINT  L: LEVELS",
            )
        elif self.modal == "result":
            footer = (
                "ENTER: NEXT  L: LEVELS  C: RESTART"
                if self.level < LEVEL_COUNT
                else "ENTER/L: LEVELS  C: RESTART"
            )
            self.draw_panel(
                f"CHAMBER {self.level} COMPLETE",
                [f"HINTS USED: {len(self.seen_hints)}"],
                footer,
            )

    def draw(self) -> None:
        self.sync_mouse()
        pyxel.cls(1)
        if self.mode == "title":
            self.draw_title()
            return
        if self.mode == "levels":
            self.draw_levels()
            return
        self.draw_room()
        self.draw_hud()
        if self.console:
            self.draw_console()
        if self.paused:
            self.draw_panel(
                "PAUSED",
                ["P RESUME  C CLEAR  L LEVELS"],
                "F11 FULLSCREEN",
            )
        if self.modal:
            self.draw_modal()
        self.draw_cursor()


def main() -> None:
    game = Game()
    pyxel.run(game.update, game.draw)
