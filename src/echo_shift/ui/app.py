"""Pyxel input, screens and rendering for the playable chambers."""

import atexit
import json
import logging
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
from echo_shift.ui.telemetry import Attempt, log_path

logger = logging.getLogger(__name__)
LEVEL_COUNT = 3
DARK_REMAP = (0, 1, 2, 1, 5, 5, 13, 13, 2, 5, 13, 3, 13, 13, 2, 5)
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
        self.text_cache = {}
        (user_data_dir() / "startup.log").write_text("Echo Shift started\n")
        self.atlas = Atlas()
        self.unlocked = load_unlocked(LEVEL_COUNT)
        self.level = 1
        self.level_cursor = 1
        self.mode = "title"
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
        self.message = "E POWER  ENTER RECORD  Q LAUNCH"
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
        self.modal = "tutorial"
        self.paused = False
        self.console = False
        self.pending = self.state.powered_circuits
        self.notice("E POWER  ENTER RECORD  Q LAUNCH")

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
        if self.mode == "title":
            if pyxel.btnp(pyxel.KEY_RETURN) or pyxel.btnp(pyxel.KEY_SPACE):
                self.mode = "levels"
            return
        if self.mode == "levels":
            if pyxel.btnp(pyxel.KEY_ESCAPE):
                self.mode = "title"
            elif pyxel.btnp(pyxel.KEY_UP) or pyxel.btnp(pyxel.KEY_W):
                self.level_cursor = max(1, self.level_cursor - 1)
            elif pyxel.btnp(pyxel.KEY_DOWN) or pyxel.btnp(pyxel.KEY_S):
                self.level_cursor = min(LEVEL_COUNT, self.level_cursor + 1)
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

    def wrapped(self, x: int, y: int, value: str, width: int, color: int = 7) -> int:
        scale = self.layout.text_scale
        chars = max(8, width // (4 * scale))
        for line in textwrap.wrap(
            value, width=chars, break_long_words=True, break_on_hyphens=False
        ):
            self.text(x, y, line, color)
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
        layout = self.layout
        self.atlas.draw(
            name,
            layout.room_x + pos.x * layout.cell,
            layout.room_y + pos.y * layout.cell,
            layout.cell,
        )

    def draw_room(self) -> None:
        state = self.state
        layout = self.layout
        lit = lighting.lit_tiles(state)
        pads = {pad.position: pad for pad in state.chamber.pads}
        devices = {device.position: device for device in state.chamber.devices}
        for y, row in enumerate(state.chamber.tiles):
            for x, tile in enumerate(row):
                pos = Position(x, y)
                dark = pos not in lit and tile is not TileType.WALL
                if dark:
                    for source, target in enumerate(DARK_REMAP):
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
                if dark:
                    pyxel.pal()
                if pos in pads or pos in devices:
                    self.text(
                        layout.room_x + x * layout.cell + 4,
                        layout.room_y + y * layout.cell + 4,
                        "A",
                        7,
                        max(1, layout.text_scale - 1),
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
        pyxel.rect(layout.panel_x, 0, 2, layout.panel_h, 6)
        x, _, width = layout.panel_content()
        unit = layout.cell / 96
        at = lambda value: round(value * unit)
        self.text(x, at(24), f"POWER {info.load}/{info.capacity}", 10)
        pyxel.rectb(x, at(55), width, max(8, at(14)), 6)
        pyxel.rect(
            x + 2,
            at(57),
            round((width - 4) * info.load / max(1, info.capacity)),
            max(4, at(10)),
            11,
        )
        self.text(x, at(91), "CIRCUITS", 10)
        for index, (name, on) in enumerate(info.circuits):
            self.wrapped(
                x,
                at(119 + index * 34),
                f"{name.upper()}: {'ON' if on else 'OFF'}",
                width,
                11 if on else 8,
            )
        self.text(x, at(245), "SAFE" if info.safe else "DARK", 11 if info.safe else 8)
        self.text(
            x + at(110), at(245), f"HINTS {len(self.seen_hints)}/{len(self.hints)}", 14
        )
        self.text(x, at(285), "ACTION", 10)
        feedback = (
            self.message if self.message_frames else self.state.phase.value.upper()
        )
        self.wrapped(x, at(311), feedback, width, 8 if self.flash else 7)
        self.text(x, at(385), "CONTROLS", 10)
        self.wrapped(x, at(410), "WASD/ARROWS MOVE  SPACE WAIT  E POWER", width)
        self.wrapped(x, at(451), "ENTER RECORD  Q LAUNCH  R RETRY  C CLEAR", width)
        self.wrapped(
            x, at(492), "T HELP  H HINT  P PAUSE  L LEVELS  F11 FULLSCREEN", width
        )
        self.text(x, at(542), "ECHO TIMELINE", 12)
        for index, ((kind, current, direction), (sx, sy, slot)) in enumerate(
            zip(info.timeline, layout.timeline_slots())
        ):
            self.atlas.draw("slot_" + kind, sx, sy, slot)
            if direction:
                self.text(
                    sx + slot - 5 * layout.text_scale,
                    sy + slot - 8 * layout.text_scale,
                    direction,
                    7,
                )
            if current:
                pyxel.rectb(sx, sy, slot, slot, 12)
            if index >= self.state.chamber.max_turns:
                pyxel.rectb(sx, sy, slot, slot, 5)
        if self.muted:
            self.text(x + width - 5 * 4 * layout.text_scale, at(24), "MUTED", 13)

    def draw_panel(
        self, title: str, lines: list[str], footer: str, show_log: bool = False
    ) -> None:
        x, y, width, height = self.layout.overlay()
        pad = max(18, self.layout.cell // 4)
        pyxel.rect(x, y, width, height, 1)
        pyxel.rectb(x, y, width, height, 12)
        self.wrapped(x + pad, y + pad, title, width - 2 * pad, 10)
        cursor = y + pad + 42 * self.layout.text_scale // 2
        for line in lines:
            cursor = (
                self.wrapped(x + pad, cursor, line, width - 2 * pad)
                + 12 * self.layout.text_scale
            )
        if show_log:
            self.draw_log_path(
                x + pad,
                y + height - pad - 75 * self.layout.text_scale // 2,
                width - 2 * pad,
            )
        self.wrapped(
            x + pad,
            y + height - pad - 12 * self.layout.text_scale,
            footer,
            width - 2 * pad,
            11,
        )

    def draw_log_path(self, x: int, y: int, width: int) -> None:
        self.text(x, y, "SEND PLAYTEST LOG:", 10)
        self.wrapped(x, y + 10 * self.layout.text_scale, str(log_path()), width)

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

    def draw_title(self) -> None:
        height = self.layout.height
        self.centered(height // 6, "ECHO SHIFT", 12, self.layout.text_scale + 4)
        self.centered(height // 3, "TURN-BASED LIGHT AND ECHO PUZZLES")
        sprite_size = min(self.layout.cell * 2, height // 3)
        middle = self.layout.width // 2
        self.atlas.draw(
            "player_idle_0", middle - sprite_size - 20, height * 2 // 5, sprite_size
        )
        self.atlas.draw("echo_idle_0", middle + 20, height * 2 // 5, sprite_size)
        self.centered(height * 3 // 4, "ENTER TO START", 10, self.layout.text_scale + 1)
        self.centered(height * 7 // 8, "M: MUTE" if not self.muted else "M: UNMUTE", 13)
        self.centered(height * 15 // 16, "F11 FULLSCREEN")

    def draw_levels(self) -> None:
        height = self.layout.height
        self.centered(height // 6, "SELECT CHAMBER", 12, self.layout.text_scale + 3)
        names = ("SAFE MOVEMENT", "POWER ALLOCATION", "RECORDING")
        for number, name in enumerate(names, 1):
            marker = ">" if self.level_cursor == number else " "
            label = name if number <= self.unlocked else "LOCKED"
            color = (
                10
                if self.level_cursor == number
                else 7
                if number <= self.unlocked
                else 5
            )
            self.centered(
                height * (number + 2) // 7,
                f"{marker} {number}. {label}",
                color,
                self.layout.text_scale + 1,
            )
        self.centered(
            height * 5 // 6, "UP/DOWN SELECT  ENTER PLAY  ESC TITLE  F11 FULLSCREEN"
        )

    def draw_modal(self) -> None:
        if self.modal == "tutorial":
            self.draw_panel(
                f"CHAMBER {self.level} - HOW TO PLAY",
                self.tutorial,
                "ENTER/T: CLOSE  H: HINT  L: LEVEL SELECT",
                show_log=True,
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
                show_log=True,
            )
        if self.modal:
            self.draw_modal()


def main() -> None:
    game = Game()
    pyxel.run(game.update, game.draw)
