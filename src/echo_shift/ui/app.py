"""Pyxel input, screens and rendering for the playable chambers."""

import atexit
import json
import logging
import math
import textwrap
from dataclasses import astuple, dataclass, replace

import pyxel

from echo_shift.engine import lighting, power, recording
from echo_shift.engine.loader import load
from echo_shift.engine.model import Phase, Position, State, TileType, initial_state
from echo_shift.engine.turn import (
    Failed,
    InteractAtConsole,
    Move,
    Rejected,
    Wait,
)
from echo_shift.paths import resource_path, user_data_dir
from echo_shift.ui import (
    audio,
    bars,
    camera,
    controls,
    cuedraw,
    cues,
    goals,
    guide,
    icon,
    motion,
    pointer,
    preview,
    progress,
    story,
)
from echo_shift.ui.atlas import Atlas
from echo_shift.ui.display import Display
from echo_shift.ui.help import pad_label, room_info, topics
from echo_shift.ui.history import History, Snapshot
from echo_shift.ui.hud import Hud, model, next_step
from echo_shift.ui.layout import Layout, framed_bounds, line_height, route_bounds
from echo_shift.ui.telemetry import Attempt
from echo_shift.ui.tutorial import (
    Tutorial,
    load_hints,
    load_steps,
    load_summary,
)

logger = logging.getLogger(__name__)
LEVEL_COUNT = 6
CHAMBER_NAMES = (
    "SAFE MOVEMENT",
    "POWER ALLOCATION",
    "RECORDING",
    "DARK REPLAY",
    "TIMED PADS",
    "FINAL ESCAPE",
)
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
PAUSE_ITEMS = (
    "pause",
    "undo",
    "retry",
    "restart",
    "rerecord",
    "levels",
    "settings",
    "controls",
    "quit_title",
)
SETTINGS_ITEMS = (
    "music_volume",
    "sfx_volume",
    "mute",
    "reduced_motion",
    "crt",
    "fullscreen",
    "close",
)
ICON_SPRITE = "player_idle_0"
ICON_SIZE = 32
ICON_SCALE = 2
SCREEN_CRISP, SCREEN_RETRO = 0, 2  # pyxel.screen_mode values
FPS = motion.FPS
PULSE_GROW = motion.PULSE_GROW
INTRO_FRAMES = 5 * FPS  # highlight for a newly shown button
MESSAGE_FRAMES = 4 * FPS  # how long a feedback line stays up
FLASH_FRAMES = FPS * 2 // 5  # the red room outline after a refusal
# Held-key repeat for the settings values, in frames (moves use the walk timing).
REPEAT_HOLD, REPEAT_RATE = FPS * 4 // 15, FPS // 6
ECHO_EVENTS = {"record": "enter", "save": "enter", "launch": "launch"}
ENTER_ACTIONS = {"enter", "launch", "apply"}
GATED_IDS = (
    "move_up",
    "move_down",
    "move_left",
    "move_right",
    "wait",
    "console",
    "echo",
    "retry",
    "undo",
)


@dataclass(frozen=True)
class FailureCard:
    reason: str
    restored: State
    kind: str
    event: str


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
        pyxel.init(
            *self.windowed_size,
            title="Echo Shift",
            fps=FPS,
            quit_key=pyxel.KEY_NONE,
            display_scale=1,
        )
        self.fullscreen = False
        self.pending_fullscreen = None
        self.layout = Layout.fit(*self.windowed_size)
        self.room_view = (self.layout.cell, self.layout.room_x, self.layout.room_y)
        self.shaken = self.room_view  # the room view with any failure shake applied
        self.room_bounds = (0, 0, 0, 0)
        self.hub_edge: tuple[object, frozenset[Position]] = (None, frozenset())
        self.camera = camera.Camera()
        self.text_cache = {}
        self.fonts = {}
        (user_data_dir() / "startup.log").write_text("Echo Shift started\n")
        self.atlas = Atlas()
        self.progress = progress.load(LEVEL_COUNT)
        self.apply_screen_mode()
        self.set_icon()
        self.audio = audio.Audio(pyxel)
        self.heard = None
        self.motion = motion.Motion(self.progress.settings.reduced_motion)
        self.move_dir = None
        self.walker = motion.Walker()
        self.played = False  # whether play input ran this frame
        self.goal_targets = goals.targets(resource_path("levels"), LEVEL_COUNT)
        self.run = None
        self.history = History()
        self.failure = None
        self.pause_index = 0
        self.level = 1
        self.level_cursor = 1
        self.mode = "title"
        self.mouse_visible = None
        self.last_menu_mouse = (-1, -1)
        self.mouse_active = False
        self.menu_mouse_moved = False
        self.modal = None
        self.lesson = None
        self.lesson_summary = ""
        self.lesson_steps = ()
        self.guide_page = 0
        self.settings_open = False
        self.settings_index = 0
        self.intro_frames = 0
        self.intro_seen = set()
        self.message_error = False
        self.modal_stack = []
        self.release_controls = False
        self.ui_hits = []
        self.choice_hits = []
        self.lesson_card_rect = (0, 0, 0, 0)
        self.hints = ()
        self.hint_index = 0
        self.seen_hints = set()
        self.browser = preview.Browser()
        self.projected = (None, None)
        self.state = initial_state(load(resource_path("levels", "chamber_01.json")))
        self.paused = False
        self.console = False
        self.terminals = ()
        self.log = None  # the terminal whose card is open
        self.log_page = 0  # how many of its lines the card shows
        self.selection = 0
        self.pending = self.state.powered_circuits
        self.message = self.play_prompt().upper()
        self.message_frames = MESSAGE_FRAMES
        self.flash = 0
        self.attempt = None
        atexit.register(self.finish_attempt)

    def finish_attempt(self, completed: bool = False) -> None:
        if self.attempt is not None:
            self.attempt.finish(completed)
            self.attempt = None

    def projection(self) -> preview.Projection | None:
        """Predictions for the current state, computed once per state."""
        if self.projected[0] is not self.state:
            self.projected = (self.state, preview.project(self.state))
        return self.projected[1]

    def preview_turn(self) -> int | None:
        """The predicted turn on show, if any."""
        if self.mode != "game" or self.console:
            return None
        return self.browser.turn(self.projection())

    def track_preview(self) -> None:
        """Count each newly opened preview once, never once per frame."""
        opened = self.browser.opened(self.preview_turn())
        if opened is not None and self.attempt is not None:
            self.attempt.record_preview(opened)

    def slot_turn_at_pointer(self) -> tuple[int | None, bool]:
        """The turn of the timeline slot under the pointer, and whether it was clicked."""
        for rect, key in self.ui_hits:
            if key.startswith("timeline:") and self.menu_hit(rect):
                turn = self.browser.slot_turn(
                    self.state, int(key.removeprefix("timeline:")), self.projection()
                )
                return turn, turn is not None and self.menu_click(rect)
        return None, False

    def open_level(self, number: int) -> None:
        self.finish_attempt()
        path = resource_path("levels", f"chamber_{number:02}.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.level = number
        self.attempt = Attempt(number)
        self.state = initial_state(load(path))
        self.terminals = story.load_terminals(data.get("terminals"), self.state.chamber)
        self.lesson_steps = load_steps(data.get("tutorial_steps"), self.state.chamber)
        self.lesson = None
        self.lesson_summary = load_summary(
            data.get("lesson_summary"), "Elevator reached."
        )
        self.guide_page = 0
        self.settings_open = False
        self.modal_stack = []
        self.release_controls = False
        self.hints = load_hints(data.get("hints"))
        self.intro_frames = (
            INTRO_FRAMES
            if number not in self.intro_seen and controls.introduced(number)
            else 0
        )
        self.intro_seen.add(number)
        self.run = None
        self.browser = preview.Browser()
        self.hint_index = 0
        self.seen_hints = set()
        self.camera.reset()
        self.mode = "game"
        self.sync_mouse()
        self.modal = "lesson_choice" if self.lesson_steps else None
        self.paused = False
        self.console = False
        self.pending = self.state.powered_circuits
        self.history.clear()
        self.failure = None
        self.notice(self.play_prompt())

    @property
    def unlocked(self) -> int:
        return self.progress.unlocked

    @property
    def muted(self) -> bool:
        return self.progress.settings.mute

    def toggle_mute(self) -> None:
        self.progress.settings.mute = not self.muted
        progress.save(self.progress)

    def unlock_next(self) -> None:
        unlocked = min(LEVEL_COUNT, self.level + 1)
        if unlocked > self.unlocked:
            self.progress.unlocked = unlocked
            progress.save(self.progress)

    def apply_screen_mode(self) -> None:
        """The optional CRT look is Pyxel's retro screen mode; off is crisp."""
        if hasattr(pyxel, "screen_mode"):
            pyxel.screen_mode(
                SCREEN_RETRO if self.progress.settings.crt else SCREEN_CRISP
            )

    def set_icon(self) -> None:
        """Window icon from the player sprite; any problem leaves the default."""
        try:
            entry = self.atlas.entries[ICON_SPRITE]
            image = self.atlas.image
            rows = icon.rows(
                lambda x, y: image.pget(entry["u"] + x, entry["v"] + y),
                entry["width"],
                entry["height"],
                ICON_SIZE,
            )
            pyxel.icon(rows, ICON_SCALE, 0)
        except Exception:
            logger.debug("window icon not set", exc_info=True)

    def modal_name(self) -> str | None:
        return (
            ("settings" if self.settings_open else "pause")
            if self.paused
            else "failure"
            if self.failure
            else self.modal or ("console" if self.console else None)
        )

    def scope(self) -> str:
        return controls.scope_for(self.mode, self.modal_name())

    def actions(self) -> list[controls.Action]:
        return controls.available_actions(
            self.state,
            self.mode,
            self.modal_name(),
            undoable=len(self.history) > 0,
            failure=self.failure.kind if self.failure else "",
            terminals=self.terminals,
        )

    def play_actions(self) -> list[controls.Action]:
        return controls.available_actions(
            self.state,
            "game",
            None,
            undoable=len(self.history) > 0,
            terminals=self.terminals,
        )

    def bar_actions(self) -> list[controls.Action]:
        """Gameplay actions the bars list in this chamber (keys always work)."""
        shown = controls.shown_actions(self.level)
        return [a for a in self.play_actions() if a.id in shown]

    def play_prompt(self, ids: tuple[str, ...] = ("console", "echo")) -> str:
        return controls.legend(self.play_actions(), ids)

    def pressed(
        self,
        action_id: str,
        *,
        repeat: bool = False,
        only: tuple[str, ...] | None = None,
    ) -> bool:
        kwargs = {"hold": REPEAT_HOLD, "repeat": REPEAT_RATE} if repeat else {}
        return any(
            pyxel.btnp(getattr(pyxel, name), **kwargs)
            for name in only or self.input_names(action_id)
            if hasattr(pyxel, name)
        )

    def input_names(self, action_id: str) -> tuple[str, ...]:
        """Keys and gamepad buttons that trigger an action in the current scope."""
        return controls.key_names(action_id) + controls.pad_names(
            action_id, self.scope()
        )

    def held(self, ids: tuple[str, ...]) -> bool:
        return hasattr(pyxel, "btn") and any(
            pyxel.btn(getattr(pyxel, name))
            for action_id in ids
            for name in self.input_names(action_id)
            if hasattr(pyxel, name)
        )

    def snapshot(self) -> Snapshot:
        return Snapshot(
            self.state,
            self.pending,
            self.console,
            self.lesson.index if self.lesson is not None else None,
        )

    def commit(self, before: Snapshot) -> None:
        """Remember `before` when an input changed anything; rejected ones don't."""
        if self.snapshot() != before:
            self.history.push(before)

    def refuse(self, action: controls.Action) -> None:
        self.attempt.record_disabled(action.id)
        self.notice(action.reason, True)

    def undo(self) -> None:
        action = controls.find(self.actions(), "undo")
        snapshot = self.history.undo()
        if snapshot is None:
            self.refuse(action)
            return
        self.state, self.pending, self.console = (
            snapshot.state,
            snapshot.pending,
            snapshot.console,
        )
        self.failure = None
        self.walker.stop()
        self.heard = audio.Cue("undo")
        self.attempt.undos += 1
        if self.lesson is not None and snapshot.lesson_index is not None:
            self.lesson.index = snapshot.lesson_index
            self.lesson.card_open = False
        self.notice("UNDONE")

    def open_guide(self, page: str | None = None) -> None:
        """Open the guide (on `page` when given), or switch page if it is open."""
        if page is not None:
            self.guide_page = guide.PAGE_IDS.index(page)
        if self.modal != "guide":
            self.modal_stack.append(self.modal)
            self.modal = "guide"

    def close_reading(self) -> None:
        self.modal = self.modal_stack.pop() if self.modal_stack else None
        self.release_controls = True

    def start_lesson(self) -> None:
        self.lesson = Tutorial(self.lesson_steps)
        self.attempt.mode = "guided"
        self.modal = None
        self.release_controls = True

    def reset_chamber(self) -> None:
        before = self.snapshot()
        self.attempt.resets += 1
        self.state = recording.clear(self.state)
        self.pending = self.state.powered_circuits
        self.console = False
        self.paused = False
        self.failure = None
        self.modal_stack = []
        if self.lesson is not None:
            self.start_lesson()
        else:
            self.modal = None
        self.commit(before)
        self.heard = audio.Cue("ui_select")
        self.notice("CHAMBER CLEARED")

    def allow(self, event: str, detail: str | None = None) -> bool:
        if self.lesson is None or self.lesson.allows(event, detail):
            return True
        self.notice("NEXT: " + self.lesson.current.say("objective"), True)
        return False

    def teach(
        self, event: str, outcome: str = "accepted", detail: str | None = None
    ) -> None:
        if self.lesson is not None and self.lesson.observe(
            event, self.state, self.pending, self.console, outcome, detail
        ):
            self.release_controls = True

    def show_hint(self) -> None:
        """Reveal the next hint and show it on the guide's Hints page."""
        self.open_guide("hints")
        if self.hint_index < len(self.hints):
            self.attempt.hints += 1
            self.seen_hints.add(self.hint_index)
            self.hint_index += 1
        else:
            self.notice("NO MORE HINTS")

    def notice(self, message: str, error: bool = False) -> None:
        if error and self.heard is None:
            self.heard = audio.Refusal(message)
        self.message_error = error
        self.message = message.upper()
        self.message_frames = MESSAGE_FRAMES
        self.flash = FLASH_FRAMES if error else 0

    def act(self, action: Move | Wait | InteractAtConsole) -> None:
        event = (
            {(1, 0): "right", (-1, 0): "left", (0, -1): "up", (0, 1): "down"}[
                (action.dx, action.dy)
            ]
            if isinstance(action, Move)
            else "wait"
            if isinstance(action, Wait)
            else "apply"
        )
        if isinstance(action, Move):
            self.move_dir = (action.dx, action.dy)
        if not self.allow(event):
            return
        if not isinstance(action, InteractAtConsole):
            gate = controls.find(
                self.actions(),
                "wait"
                if isinstance(action, Wait)
                else pointer.MOVES[action.dx, action.dy],
            )
            if not gate.enabled:
                self.refuse(gate)
                return
        result = self.heard = recording.act(self.state, action)
        outcome = (
            "rejected"
            if isinstance(result, Rejected)
            else "failed"
            if isinstance(result, Failed)
            else "accepted"
        )
        shown = result.state
        details = (
            f"action={action!r} outcome={outcome} phase={shown.phase.value} "
            f"turn={shown.turns} player=({shown.player.x},{shown.player.y}) "
            f"echo={shown.echo_position} powered={sorted(shown.powered_circuits)} "
            f"gates_open={sorted(shown.gates_open)} "
            f"elevators_running={sorted(shown.elevators_running)}"
        )
        if isinstance(result, Failed):
            self.history.push(self.snapshot())
            self.failure = FailureCard(
                result.reason,
                result.state,
                "recording" if self.state.phase is Phase.RECORDING else "replay",
                event,
            )
            self.console = False
            self.release_controls = True
            self.attempt.resets += 1
            logger.warning("%s reason=%s", details, result.reason)
            self.notice(f"FAILED: {result.reason}", True)
            return
        self.state = result.state
        if isinstance(result, Rejected):
            logger.warning("%s reason=%s", details, result.reason)
            self.notice(result.reason, True)
        else:
            logger.info("%s", details)
            if result.succeeded:
                self.finish_attempt(completed=True)
                self.run = goals.run_of(self.state)
                if goals.record(self.progress, self.level, self.run):
                    progress.save(self.progress)
                self.unlock_next()
                self.modal = "result"
                self.notice("ELEVATOR REACHED!")
        if isinstance(action, InteractAtConsole) and not isinstance(result, Rejected):
            self.console = False
        self.teach(event, outcome)

    def update(self) -> None:
        self.browser.hover = None
        if self.mode == "game" and self.modal != "lesson_choice":
            self.intro_frames = max(0, self.intro_frames - 1)
        self.motion.set_reduced(self.progress.settings.reduced_motion)
        self.track_device()
        if self.gameplay_input():
            self.motion.snap()  # new input ends running animations first
        before, seen, mode = self.state, self.ui_marks(), self.mode
        self.heard = self.move_dir = None
        self.played = False
        self.step_frame()
        self.track_preview()
        self.animate(before, mode)
        self.motion.set_drawer(
            self.console, self.mode == mode and self.state.chamber is before.chamber
        )
        self.hear(before, seen)
        self.walker.tick(self.played)
        self.motion.tick()

    def gameplay_input(self) -> bool:
        """Whether any gameplay key, pad or mouse button went down this frame."""
        names = (
            *controls.gameplay_key_names(),
            *controls.gameplay_pad_names(),
            "MOUSE_BUTTON_LEFT",
        )
        return self.any_down(names)

    def any_down(self, names: tuple[str, ...]) -> bool:
        if not hasattr(pyxel, "btnp"):
            return False
        return any(pyxel.btnp(getattr(pyxel, n)) for n in names if hasattr(pyxel, n))

    def track_device(self) -> None:
        """Labels follow the device used last: pad glyphs or key names."""
        if self.any_down(controls.all_pad_names()):
            controls.set_device("pad")
        elif self.any_down((*controls.all_key_names(), "MOUSE_BUTTON_LEFT")):
            controls.set_device("keys")

    def animate(self, before: State, mode: str) -> None:
        """Start motion from what this frame changed; presentation only."""
        if self.mode != mode or self.state.chamber is not before.chamber:
            self.motion.fade_in()
        elif isinstance(self.heard, audio.Cue) and self.heard.sfx_id == "undo":
            self.motion.start(before, self.state, undo=True)
        elif isinstance(self.heard, audio.Cue):
            self.motion.snap()  # restarts show their result at once
            self.motion.forget()
        elif (
            self.state is not before
            or self.move_dir is not None
            or isinstance(self.heard, Failed)
        ):
            self.motion.start(before, self.state, self.heard, self.move_dir)

    def ui_marks(self) -> tuple:
        """What menus, cards and the console show, to tell what an input changed."""
        lesson = self.lesson
        return (
            (
                self.mode,
                self.modal,
                self.paused,
                self.settings_open,
                self.console,
                self.failure is not None,
                astuple(self.progress.settings),
            ),
            (
                (lesson.index, lesson.card_open) if lesson is not None else None,
                self.log_page,
            ),
            (
                self.level_cursor,
                self.pause_index,
                self.settings_index,
                self.selection,
                self.guide_page,
            ),
            self.pending,
        )

    def ui_cue(self, seen: tuple) -> str | None:
        screen, card, cursor, pending = self.ui_marks()
        if card != seen[1] and seen[0][1] == "log":
            return "dialogue"  # a log line was shown, or the last one closed it
        if screen != seen[0]:
            return "ui_select"
        if card != seen[1]:
            return "dialogue"
        if pending != seen[3]:
            return "power_on" if len(pending) > len(seen[3]) else "power_off"
        return "ui_hover" if cursor != seen[2] else None

    def hear(self, before: State, seen: tuple) -> None:
        """The one place effects and music follow the game: an engine result or a
        refusal, else a menu change, then the state difference (`audio.sfx_for`)."""
        cue = self.heard if self.heard is not None else self.ui_cue(seen)
        self.audio.apply_settings(self.progress.settings)
        self.audio.on_transition(before, cue, self.state)
        self.audio.sync_music(
            audio.music_for(
                self.mode, self.modal, self.state.phase, self.level, LEVEL_COUNT
            )
        )

    def step_frame(self) -> None:
        self.sync_display()
        self.sync_mouse()
        if self.pressed("fullscreen"):
            self.toggle_fullscreen()
            return
        if (
            any(pyxel.btn(getattr(pyxel, name)) for name in controls.MODIFIER_KEYS)
            if hasattr(pyxel, "btn")
            else False
        ):
            return
        self.message_frames = max(0, self.message_frames - 1)
        self.flash = max(0, self.flash - 1)
        if self.pressed("mute"):
            self.toggle_mute()
        if self.mode in ("title", "levels"):
            pointer = self.menu_mouse_position()
            self.menu_mouse_moved = pointer != self.last_menu_mouse
            if self.menu_mouse_moved:
                self.mouse_active = True
            self.last_menu_mouse = pointer
        if self.mode == "title":
            if self.pressed("confirm") or self.menu_click(self.layout.start_button()):
                self.mode = "levels"
            return
        if self.mode == "levels":
            hovered = self.hovered_chamber()
            if self.menu_mouse_moved and hovered is not None:
                self.level_cursor = hovered
            if self.pressed("close"):
                self.mode = "title"
            elif self.pressed("nav_prev"):
                self.level_cursor = max(1, self.level_cursor - 1)
                self.mouse_active = False
            elif self.pressed("nav_next"):
                self.level_cursor = min(LEVEL_COUNT, self.level_cursor + 1)
                self.mouse_active = False
            elif hovered is not None and self.menu_click(
                self.layout.chamber_cards(LEVEL_COUNT)[hovered - 1]
            ):
                if hovered <= self.unlocked:
                    self.open_level(hovered)
            elif self.pressed("confirm") and self.level_cursor <= self.unlocked:
                self.open_level(self.level_cursor)
            return
        if self.modal == "result":
            clicked = self.clicked_row()
            if self.pressed("confirm") or clicked == "result:confirm":
                if self.level < LEVEL_COUNT:
                    self.open_level(self.level + 1)
                else:
                    self.show_levels()
            elif self.pressed("close") or clicked == "result:close":
                self.show_levels()
            elif self.pressed("restart") or clicked == "result:restart":
                self.open_level(self.level)
            return
        if self.failure is not None:
            self.failure_input()
            return
        if self.paused:
            self.pause_input()
            return
        if self.pause_pressed():
            self.perform("pause")
            return
        # Navigation and reading controls remain available during every lesson step.
        if self.pressed("restart"):
            self.perform("restart")
            return
        if self.pressed("guide"):
            self.perform("guide")
            return
        if self.pressed("hint"):
            self.perform("hint")
            return
        if self.modal == "lesson_choice":
            if self.pressed("confirm") or (
                self.choice_hits and self.menu_click(self.choice_hits[0])
            ):
                self.start_lesson()
            elif self.pressed("free_play") or (
                len(self.choice_hits) > 1 and self.menu_click(self.choice_hits[1])
            ):
                self.attempt.mode = "free"
                self.modal = None
                self.release_controls = True
            return
        if self.modal == "guide":
            self.guide_input()
            return
        if self.modal == "log":
            self.log_input()
            return
        if self.lesson is not None and self.lesson.card_open and self.dismiss_card():
            return
        # All gameplay keys must be released after reading before another action.
        if self.release_controls:
            if self.held(GATED_IDS):
                return
            self.release_controls = False
        clicked_slot = False
        if not self.console:
            self.browser.hover, clicked_slot = self.slot_turn_at_pointer()
        if self.pressed("undo"):
            self.perform("undo")
        elif self.console:
            before = self.snapshot()
            self.console_input()
            if self.failure is None:
                self.commit(before)
        elif clicked_slot:
            self.browser.chosen = self.browser.hover
        elif (
            clicked := self.clicked_action() or self.clicked_tile_action()
        ) is not None:
            self.perform(clicked)
        else:
            self.play_input()

    def show_levels(self) -> None:
        self.finish_attempt()
        self.mode = "levels"
        self.level_cursor = self.level
        self.modal = None
        self.paused = False
        self.console = False

    def dismiss_card(self) -> bool:
        """Close a concept card on Enter or a click. True when the input is used up.

        Enter also performs the step's own action when that action uses Enter.
        """
        clicked = self.menu_click(self.lesson_card_rect)
        if not clicked and not self.pressed("apply"):
            return False
        self.lesson.card_open = False
        return clicked or self.lesson.current.action not in ENTER_ACTIONS

    def guide_input(self) -> None:
        clicked = self.clicked_row()
        count = len(guide.PAGES)
        if self.pressed("nav_next") or clicked == "guide:next":
            self.guide_page = (self.guide_page + 1) % count
        elif self.pressed("nav_prev") or clicked == "guide:prev":
            self.guide_page = (self.guide_page - 1) % count
        elif clicked is not None and clicked.startswith("guide:page:"):
            self.guide_page = int(clicked.removeprefix("guide:page:"))
        elif (
            self.pressed("close") or self.pressed("confirm") or clicked == "guide:close"
        ):
            self.close_reading()

    def log_input(self) -> None:
        """Space, Enter or a click shows the next line, then closes; Esc, E or a
        right click closes at once. Reading never touches the chamber."""
        if self.pressed("close"):
            self.modal = None
            self.release_controls = True
        elif self.pressed("confirm") or (
            hasattr(pyxel, "MOUSE_BUTTON_LEFT") and pyxel.btnp(pyxel.MOUSE_BUTTON_LEFT)
        ):
            self.log_page += 1
            if self.log_page > len(self.log.lines):
                self.modal = None
                self.release_controls = True

    def pause_pressed(self) -> bool:
        if self.console or self.modal in ("guide", "log"):
            return False  # Esc closes the overlay first.
        return self.pressed("pause")

    def pause_input(self) -> None:
        if self.settings_open:
            self.settings_input()
            return
        clicked = self.clicked_row()
        if self.pressed("pause") or self.pressed(
            "close", only=(controls.RIGHT_CLICK, *controls.pad_names("close"))
        ):
            self.paused = False
        elif clicked is not None and clicked.startswith("pause:"):
            action_id = clicked.removeprefix("pause:")
            self.pause_index = PAUSE_ITEMS.index(action_id)
            self.pause_choose(action_id)
        elif self.pressed("nav_prev"):
            self.pause_index = (self.pause_index - 1) % len(PAUSE_ITEMS)
        elif self.pressed("nav_next"):
            self.pause_index = (self.pause_index + 1) % len(PAUSE_ITEMS)
        elif self.pressed("confirm"):
            self.pause_choose(PAUSE_ITEMS[self.pause_index])
        else:
            for action_id in PAUSE_ITEMS:
                keyed = controls.BINDINGS[action_id].keys
                if action_id != "pause" and keyed and self.pressed(action_id):
                    self.pause_choose(action_id)
                    break

    def pause_choose(self, action_id: str) -> None:
        action = controls.find(self.actions(), action_id)
        if not action.enabled:
            self.refuse(action)
            return
        if action_id == "settings":
            self.settings_open = True
            self.settings_index = 0
            return
        before = self.snapshot()
        self.paused = False
        if action_id == "undo":
            self.undo()
        elif action_id == "retry":
            self.retry()
        elif action_id == "restart":
            self.reset_chamber()
        elif action_id == "rerecord":
            self.rerecord()
        elif action_id == "levels":
            self.show_levels()
        elif action_id == "controls":
            self.open_guide("controls")
            self.release_controls = True
        elif action_id == "quit_title":
            self.finish_attempt()
            self.mode = "title"
        if action_id in ("retry", "rerecord"):
            self.commit(before)

    def settings_value(self, item: str) -> str:
        settings = self.progress.settings
        if item in ("music_volume", "sfx_volume"):
            return f"< {getattr(settings, item)}/{progress.MAX_VOLUME} >"
        if item == "fullscreen":
            return "ON" if self.fullscreen else "OFF"
        return "ON" if getattr(settings, item, False) else "OFF"

    def change_setting(self, item: str, step: int = 0, wrap: bool = False) -> None:
        """Step a volume by `step`, or flip a switch; changes are saved at once."""
        settings = self.progress.settings
        if item in ("music_volume", "sfx_volume"):
            value = getattr(settings, item) + step
            top = progress.MAX_VOLUME
            setattr(
                settings, item, value % (top + 1) if wrap else max(0, min(top, value))
            )
        elif item == "fullscreen":
            self.toggle_fullscreen()
            return
        elif item in ("mute", "reduced_motion", "crt"):
            setattr(settings, item, not getattr(settings, item))
            if item == "crt":
                self.apply_screen_mode()
        else:
            return
        progress.save(self.progress)

    def settings_click(self) -> tuple[str, int] | None:
        """The setting row just clicked and the side (-1 left half, +1 right half)."""
        for rect, key in self.ui_hits:
            if key.startswith("row:setting:") and self.menu_click(rect):
                side = (
                    1 if self.menu_mouse_position()[0] >= rect[0] + rect[2] // 2 else -1
                )
                return key.removeprefix("row:setting:"), side
        return None

    def settings_input(self) -> None:
        item = SETTINGS_ITEMS[self.settings_index]
        clicked = self.settings_click()
        if self.pressed("close") or self.pressed("pause"):
            self.settings_open = False
        elif clicked is not None:
            item, side = clicked
            self.settings_index = SETTINGS_ITEMS.index(item)
            if item == "close":
                self.settings_open = False
            else:
                self.change_setting(item, side)
        elif self.pressed("row_prev"):
            self.settings_index = (self.settings_index - 1) % len(SETTINGS_ITEMS)
        elif self.pressed("row_next"):
            self.settings_index = (self.settings_index + 1) % len(SETTINGS_ITEMS)
        elif self.pressed("value_down", repeat=True):
            self.change_setting(item, -1)
        elif self.pressed("value_up", repeat=True):
            self.change_setting(item, 1)
        elif self.pressed("confirm"):
            if item == "close":
                self.settings_open = False
            else:
                self.change_setting(item, 1, wrap=True)

    def failure_input(self) -> None:
        if self.release_controls:
            if self.held(GATED_IDS):
                return
            self.release_controls = False
        failure = self.failure
        clicked = self.clicked_row()
        if self.pressed("undo") or clicked == "failure:undo":
            self.attempt.record_failure_choice("undo")
            self.undo()
        elif self.pressed("restart") or clicked == "failure:restart":
            self.attempt.record_failure_choice("restart")
            self.reset_chamber()
        elif clicked == "failure:retry" or any(
            self.pressed(action_id, repeat=action_id.startswith("move"))
            for action_id in controls.SCOPES["play"]
            if action_id not in ("undo", "restart", "mute", "fullscreen")
            and controls.BINDINGS[action_id].keys
        ):
            if (
                self.pressed("retry") or clicked == "failure:retry"
            ) and failure.kind != "replay":
                self.attempt.record_disabled("retry")
            self.attempt.record_failure_choice("retry")
            self.failure = None
            self.state = failure.restored
            self.pending = self.state.powered_circuits
            self.release_controls = True
            self.notice(
                "RETRY FROM LAUNCH" if failure.kind == "replay" else "TAKE DISCARDED"
            )
            self.teach(failure.event, "failed")

    def retry(self) -> None:
        action = controls.find(self.actions(), "retry")
        if not action.enabled:
            self.refuse(action)
            return
        self.state = recording.retry(self.state)
        self.attempt.resets += 1
        self.notice("RETRY FROM LAUNCH")
        self.pending = self.state.powered_circuits
        if self.lesson is not None:
            if self.lesson.allows("retry"):
                self.teach("retry")
            else:
                self.lesson.rewind()
                self.release_controls = True

    def rerecord(self) -> None:
        action = controls.find(self.play_actions(), "rerecord")
        if not self.allow("rerecord"):
            return
        if not action.enabled:
            self.refuse(action)
            return
        self.state = initial_state(
            self.state.chamber, self.state.powered_circuits, self.state.cells_taken
        )
        self.pending = self.state.powered_circuits
        self.console = False
        self.heard = audio.Cue("ui_select")
        self.notice("RECORDING DISCARDED")

    def echo_key(self, alias: bool = False) -> None:
        action = controls.find(self.actions(), "echo")
        verb = controls.echo_verb(self.state)
        if not self.allow(ECHO_EVENTS.get(verb, "enter")):
            return
        if verb is None or (alias and verb != "launch"):
            if verb is not None:
                action = replace(
                    action,
                    enabled=False,
                    reason="Nothing to launch yet; save a recording first",
                )
            self.refuse(action)
            return
        before = self.state
        self.state = (
            recording.launch(before) if verb == "launch" else recording.enter(before)
        )
        if self.state is before:
            self.notice("NOTHING CHANGED", True)
            return
        if verb == "launch":
            self.notice("ECHO LAUNCHED: REACH THE ELEVATOR")
        else:
            self.notice(
                "RECORDING: " + self.play_prompt(("echo",))
                if verb == "record"
                else "COMMITTED: " + self.play_prompt(("console", "echo"))
            )
        self.teach(ECHO_EVENTS[verb])

    def open_log(self, terminal: story.Terminal) -> None:
        self.log, self.log_page = terminal, 1
        self.modal = "log"

    def open_console(self, *, power: bool = False) -> None:
        """Open the console, or read a log in reach; a click on the tile only powers."""
        terminals = () if power else self.terminals
        if (terminal := story.in_reach(self.state, terminals)) is not None:
            self.open_log(terminal)
            return
        if not self.allow("open_console"):
            return
        action = controls.find(
            controls.available_actions(self.state, "game", None, terminals=terminals)
            if power
            else self.actions(),
            "console",
        )
        if action.enabled:
            self.console = True
            self.pending = self.state.powered_circuits
            self.selection = 0
            self.teach("open_console")
        else:
            self.refuse(action)

    def perform(self, action_id: str, *, alias: bool = False) -> None:
        """Run one gameplay action; keys and bar buttons both come through here."""
        if action_id in ("preview_prev", "preview_next"):
            action = controls.find(self.play_actions(), action_id)
            if action.enabled:
                self.browser.step(
                    self.projection(), 1 if action_id == "preview_next" else -1
                )
            else:
                self.refuse(action)
            return
        self.browser.release()
        if action_id == "undo":
            self.undo()
        elif action_id == "restart":
            self.reset_chamber()
        elif action_id == "pause":
            self.paused = True
            self.pause_index = 0
        elif action_id == "guide":
            if self.modal == "guide":
                self.close_reading()
            else:
                self.open_guide("goal")
            self.release_controls = True
        elif action_id == "hint":
            self.show_hint()
            self.release_controls = True
        else:
            before = self.snapshot()
            if action_id == "retry":
                self.retry()
            elif action_id in ("console", pointer.POWER):
                self.open_console(power=action_id == pointer.POWER)
            elif action_id == pointer.READ_LOG:
                self.open_console()
            elif action_id == "echo":
                self.echo_key(alias)
            elif action_id == "rerecord":
                self.rerecord()
            elif action_id == "wait":
                self.act(Wait())
            else:
                self.act(Move(*controls.MOVE_DELTAS[action_id]))
            if self.failure is None:
                self.commit(before)

    def play_input(self) -> None:
        if self.pressed("retry"):
            self.perform("retry")
        elif self.pressed("console"):
            self.perform("console")
        elif self.pressed("echo", only=controls.BINDINGS["echo"].hidden):
            self.perform("echo", alias=True)
        elif self.pressed("echo"):
            self.perform("echo")
        elif self.pressed("wait"):
            self.perform("wait")
        elif self.pressed("preview_prev"):
            self.perform("preview_prev")
        elif self.pressed("preview_next"):
            self.perform("preview_next")
        else:
            self.walk_input()

    def walk_input(self) -> None:
        """A fresh press steps at once; a held key steps again as each glide lands."""
        self.played = True
        moves = tuple(controls.MOVE_DELTAS)
        for action_id in moves:
            if self.pressed(action_id):
                self.walk(action_id)
                return
        for action_id in moves:
            if self.walker.repeats(
                action_id,
                self.held((action_id,)),
                controls.find(self.actions(), action_id).enabled,
            ):
                self.walk(action_id)
                return

    def walk(self, action_id: str) -> None:
        before = self.state.player
        self.perform(action_id)
        self.walker.stepped(
            action_id, self.failure is None and self.state.player != before
        )

    def clicked_action(self) -> str | None:
        """The gameplay action a click on the bars asks for, if any."""
        for rect, key in reversed(self.ui_hits):
            if self.menu_click(rect):
                if key.startswith("action:"):
                    return key.removeprefix("action:")
                if key == "power" or key.startswith("circuit:"):
                    return "console"
        return None

    def clicked_tile_action(self) -> str | None:
        """The gameplay action a left click on a room tile asks for, if any."""
        if not (
            hasattr(pyxel, "MOUSE_BUTTON_LEFT") and pyxel.btnp(pyxel.MOUSE_BUTTON_LEFT)
        ):
            return None
        tile = self.pointer_tile(self.shaken)
        if tile is None:
            return None
        return pointer.click_action(self.state, tile, self.terminals)

    def clicked_row(self) -> str | None:
        """The key of the panel row (without its "row:" prefix) just clicked."""
        for rect, key in self.ui_hits:
            if key.startswith("row:") and self.menu_click(rect):
                return key.removeprefix("row:")
        return None

    def toggle_selected(self) -> None:
        name = self.state.chamber.circuits[self.selection].id
        if self.allow("toggle", name):
            self.pending = frozenset(self.pending ^ {name})
            if not controls.stages_power(self.state):
                self.apply_free_power()
            self.teach("toggle", detail=name)

    def apply_console(self) -> None:
        if not self.allow("apply"):
            return
        if not power.apply(
            self.state.chamber, self.pending, power.capacity_of(self.state)
        ).ok:
            if controls.stages_power(self.state):
                self.attempt.unsafe_power_choices += 1  # free mode counted it
            self.notice("OVER BUDGET - REMOVE A CIRCUIT", True)
            self.teach("apply", "rejected")
        elif self.pending == self.state.powered_circuits:
            self.console = False
            self.teach("apply")
        else:
            self.act(InteractAtConsole(self.pending))

    def console_input(self) -> None:
        circuits = self.state.chamber.circuits
        clicked = self.clicked_row()
        if clicked is not None and clicked.startswith("circuit:"):
            ids = [circuit.id for circuit in circuits]
            self.selection = ids.index(clicked.removeprefix("circuit:"))
            self.toggle_selected()
        elif clicked == "apply":
            self.apply_console()
        elif self.pressed("close"):
            if self.lesson is None:
                self.console = False
            else:
                self.notice("NEXT: " + self.lesson.current.say("objective"), True)
        elif self.pressed("nav_prev"):
            self.selection = (self.selection - 1) % len(circuits)
        elif self.pressed("nav_next"):
            self.selection = (self.selection + 1) % len(circuits)
        elif self.pressed("toggle"):
            self.toggle_selected()
        elif self.pressed("apply"):
            self.apply_console()
        elif self.lesson is not None and self.pressed("retry"):
            self.notice("NEXT: " + self.lesson.current.say("objective"), True)

    def apply_free_power(self) -> None:
        """Preparation and committed power changes take effect at once, for free."""
        if self.pending == self.state.powered_circuits:
            return
        if not power.apply(
            self.state.chamber, self.pending, power.capacity_of(self.state)
        ).ok:
            self.attempt.unsafe_power_choices += 1
            self.notice("OVER BUDGET - REMOVE A CIRCUIT", True)
            return
        result = recording.act(self.state, InteractAtConsole(self.pending))
        if isinstance(result, Rejected):
            self.notice(result.reason, True)
            return
        self.state = result.state
        hud = model(self.state)
        self.notice(f"POWER {hud.load}/{hud.capacity}")

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
            y += self.line_height(scale)
        return y

    def centered(
        self, y: int, value: str, color: int = 7, scale: int | None = None
    ) -> None:
        scale = scale or self.layout.text_scale
        self.text(
            (self.layout.width - len(value) * 4 * scale) // 2, y, value, color, scale
        )

    def sprite(self, name: str, pos: Position | tuple[float, float]) -> None:
        cell, x, y = self.shaken
        tx, ty = pos if isinstance(pos, tuple) else (pos.x, pos.y)
        self.atlas.draw(name, x + tx * cell, y + ty * cell, cell)

    def pointer_tile(self, view: cuedraw.View) -> Position | None:
        """The room tile under the pointer, or None off the room or under the drawer."""
        mx, my = self.menu_mouse_position()
        x, _, width, _ = self.layout.console_drawer()
        hidden = self.motion.drawer_hidden()
        drawer = None
        if hidden is not None:  # sliding: the edge where the drawer is drawn
            drawer = x + round(hidden * width)
        elif self.console:
            drawer = x
        return pointer.tile_at(view, self.room_bounds, self.layout.room, mx, my, drawer)

    def draw_room(self) -> None:
        state = self.state
        layout = self.layout
        lit = lighting.lit_tiles(state)
        pads = {pad.position: pad for pad in state.chamber.pads}
        devices = {device.position: device for device in state.chamber.devices}
        if self.hub_edge[0] is not state.chamber:
            self.hub_edge = (state.chamber, cues.hub_thresholds(state.chamber))
        hub_edge = self.hub_edge[1]
        left_x, top_y, right_x, bottom_y = route_bounds(state.chamber)
        route = {
            Position(x, y)
            for y, row in enumerate(state.chamber.tiles)
            for x, tile in enumerate(row)
            if tile is not TileType.WALL
        }
        bounds = framed_bounds(state.chamber)
        port = layout.room_viewport(self.console)
        cell = layout.tile_size(bounds[2] - bounds[0] + 1, bounds[3] - bounds[1] + 1)
        shown_x, shown_y, _ = self.motion.player(state.player)
        view_at = self.camera.follow(
            (shown_x + 0.5, shown_y + 0.5),
            (port[2] / cell, port[3] / cell),
            bounds,
            (cell, layout.room),
            self.progress.settings.reduced_motion,
        )
        origin_x, origin_y = camera.view_origin(port, cell, view_at)
        view = (cell, origin_x, origin_y)
        self.room_view = view
        self.room_bounds = bounds
        shake_x, shake_y = self.motion.shake()
        origin_x += round(shake_x * cell)
        origin_y += round(shake_y * cell)
        view = self.shaken = (cell, origin_x, origin_y)
        hover = self.pointer_tile(view)
        pyxel.clip(*layout.room)
        seen = camera.visible_tiles(view, layout.room, bounds)
        min_x, min_y, max_x, max_y = seen if seen else (0, 0, -1, -1)
        turn = self.preview_turn()
        frame = self.projection().at(turn) if turn is not None else None
        live = frame is None  # motion only shows real steps, not previews
        active = frame.pads_active if frame else state.pad_active
        gates_open = frame.gates_open if frame else state.gates_open
        running = frame.elevators_running if frame else state.elevators_running
        timers = frame.timers if frame else state.pad_timers
        occupied = frame.pads_occupied if frame else state.pad_occupied
        focus = {
            link.device.id: link
            for link in (() if self.console else cues.focused_links(state, hover))
        }
        letter = max(1, min(4, cell // 40))
        letter_char = self.char_width(letter)
        terminal_tiles = {terminal.position for terminal in self.terminals}
        conduit_tiles = {tile for c in state.chamber.conduits for tile in c.tiles}
        hot_tiles = lighting.live_conduit_tiles(state)
        cell_tiles = {
            c.position for c in state.chamber.cells if c.id not in state.cells_taken
        }
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                tile = state.chamber.tiles[y][x]
                pos = Position(x, y)
                hot = pos in hot_tiles  # a live conduit glows, lit or not
                dark = pos not in lit and tile is not TileType.WALL and not hot
                distant_wall = tile is TileType.WALL and not any(
                    Position(x + dx, y + dy) in route
                    for dx, dy in ((0, 0), *cues.STEPS)
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
                names = [
                    "wall"
                    if tile is TileType.WALL
                    else ("floor_hub" if pos in hub_edge else "floor_hub_inner")
                    if pos in state.chamber.hub
                    else ("conduit_live" if hot else "conduit_off")
                    if pos in conduit_tiles
                    else "floor_lit"
                ]
                if pos in pads:
                    pad = pads[pos]
                    prefix = "pad_timed" if pad.timer_length else "pad"
                    names.append(
                        (live and self.motion.pad(pad.id))
                        or prefix + ("_on" if pad.id in active else "_off")
                    )
                elif pos in devices:
                    device = devices[pos]
                    if device.kind is TileType.GATE:
                        names.append(
                            (live and self.motion.gate(device.id))
                            or (
                                "gate_open"
                                if device.id in gates_open
                                else "gate_closed"
                            )
                        )
                    else:
                        names.append(
                            (live and self.motion.elevator(device.id))
                            or (
                                "elevator_on"
                                if device.id in running
                                else "elevator_off"
                            )
                        )
                elif pos in state.chamber.consoles:
                    names.append(
                        "console_1" if self.motion.console_lit() else "console"
                    )
                elif pos in terminal_tiles:
                    names.append("terminal")
                # A tile whose light just changed shows its old look, then fades
                # to the new one with a dither.
                looks = ((dark, 1.0),)
                fading = self.motion.light(pos) if live and not hot else None
                if fading and tile is not TileType.WALL:
                    looks = ((not fading[0], 1.0), (dark, fading[1]))
                for look_dark, alpha in looks:
                    if look_dark:
                        for source, target in enumerate(DARK_REMAP):
                            pyxel.pal(source, target)
                    pyxel.dither(alpha)
                    for name in names:
                        self.sprite(name, pos)
                    pyxel.dither(1.0)
                    if look_dark:
                        pyxel.pal()
                if pos in cell_tiles:  # cells glow in the dark too
                    self.sprite("cell", (x, y - self.motion.breath(x * 7 + y * 3)))
                if pos in pads or pos in devices:
                    pad_id = pads[pos].id if pos in pads else devices[pos].pad_id
                    link = focus.get(devices[pos].id) if pos in devices else None
                    cuedraw.badge(
                        view,
                        pos,
                        self.text,
                        pad_label(state, pad_id),
                        letter,
                        letter_char,
                        pad_id in active,
                        link.powered if link else None,
                    )
        if live:
            self.draw_dust(lit, (min_x, min_y, max_x, max_y), view)
        left = origin_x + left_x * cell
        right = origin_x + (right_x + 1) * cell
        top = origin_y + top_y * cell
        bottom = origin_y + (bottom_y + 1) * cell
        rail = max(2, cell // 32)
        pyxel.rect(left, top - rail * 3, right - left, rail, 5)
        pyxel.rect(left, bottom + rail * 2, right - left, rail, 5)
        if state.powered_circuits and (travelled := self.motion.conduit()) is not None:
            # The rails are the only drawn conduit, so a powered chamber pulses there.
            pulse = max(rail * 6, cell // 2)
            for rail_y, share in (
                (top - rail * 3, travelled),
                (bottom + rail * 2, 1.0 - travelled),
            ):
                pyxel.rect(
                    left + round((right - left - pulse) * share),
                    rail_y,
                    pulse,
                    rail,
                    12,
                )
        for edge in (left, right - rail * 2):
            pyxel.rect(edge, top - rail * 5, rail * 2, rail * 5, 12)
            pyxel.rect(edge, bottom, rail * 2, rail * 5, 9)
        self.draw_cues(view, frame, timers, occupied, focus, letter, letter_char)
        flicker = motion.blink(getattr(pyxel, "frame_count", 0), 0.4)
        if frame is not None:
            self.draw_ghosts(view, frame, flicker)
        elif (shown := self.motion.echo(state.echo_position)) is not None:
            for alpha, at in zip(
                motion.TRAIL_ALPHA, self.motion.trail(state.echo_position)
            ):
                for colour in range(1, 16):
                    pyxel.pal(colour, 13)
                pyxel.dither(alpha)
                self.sprite("echo_idle_0", at)
                pyxel.dither(1.0)
                pyxel.pal()
            lift = 0.0 if shown[2] else self.motion.breath(motion.FPS // 2)
            self.sprite(shown[2] or f"echo_idle_{flicker}", (shown[0], shown[1] - lift))
        x, y, name = self.motion.player(state.player)
        lift = 0.0 if name else self.motion.breath()
        self.sprite(name or f"player_idle_{flicker}", (x, y - lift))
        if frame is None and (command := preview.next_command(state)):
            cuedraw.arrow(view, state.echo_position, command)
        covered = self.paused or self.failure or self.modal or self.console
        if (
            hover is not None
            and not covered
            and pointer.hover_action(state, hover, self.play_actions(), self.terminals)
        ):
            pyxel.rectb(
                origin_x + hover.x * cell + 1,
                origin_y + hover.y * cell + 1,
                cell - 2,
                cell - 2,
                7,
            )
        if (sparks := self.motion.burst()) is not None:
            cuedraw.burst(view, (sparks[0].x, sparks[0].y), sparks[1])
        for at, sparks in self.motion.sparkles():
            cuedraw.burst(view, (at.x, at.y), sparks)
        cuedraw.offscreen(
            view,
            port,
            cues.offscreen_targets(state, self.motion.echo(state.echo_position)),
        )
        if edge := self.motion.vignette():
            cuedraw.vignette(
                (layout.room_x, layout.room_y, layout.room_w, layout.room_h), edge
            )
        if self.flash and not self.progress.settings.reduced_motion:
            pyxel.rectb(layout.room_x, layout.room_y, layout.room_w, layout.room_h, 8)
        pyxel.clip()

    def draw_dust(self, lit: frozenset[Position], bounds, view) -> None:
        """A few motes drifting over the lit floor."""
        min_x, min_y, max_x, max_y = bounds
        floor = sorted(
            (p for p in lit if min_x <= p.x <= max_x and min_y <= p.y <= max_y),
            key=lambda p: (p.y, p.x),
        )
        cell, origin_x, origin_y = view
        size = max(1, cell // 48)
        for mote in self.motion.dust() if floor else ():
            at = floor[mote.pick % len(floor)]
            pyxel.rect(
                origin_x + round((at.x + mote.x) * cell),
                origin_y + round((at.y + mote.y) * cell),
                size,
                size,
                mote.colour,
            )

    def draw_cues(
        self, view, frame, timers, occupied, focus, letter: int, letter_char: int
    ) -> None:
        """Safety, timing and link cues drawn over the tiles, under the sprites."""
        state = self.state
        devices = {device.id: device.position for device in state.chamber.devices}
        if state.phase in preview.PREVIEW_PHASES and not self.console:
            cuedraw.path_dots(view, preview.echo_path(state))
        if not self.console:
            warn = cues.warns_unsafe(state)
            for tile in cues.unsafe_neighbours(state):
                cuedraw.unsafe_outline(view, tile, warn)
            for link in focus.values():
                cuedraw.links(view, (link,), self.layout.room)
            marks = preview.markers(state)
            numbers = preview.countdowns(state.chamber, timers, occupied)
            positions = {pad.id: pad.position for pad in state.chamber.pads}
            for pad_id, value in numbers:
                cuedraw.countdown(
                    view,
                    positions[pad_id],
                    self.text,
                    value,
                    letter,
                    letter_char,
                    self.motion.tick_lift(pad_id) if frame is None else 0.0,
                )
            if frame is None:
                kinds = {d.id: d.kind for d in state.chamber.devices}
                for device_id in sorted(marks.closing):
                    cuedraw.closing(
                        view,
                        devices[device_id],
                        self.text,
                        self.char_width(1),
                        "CLOSES" if kinds[device_id] is TileType.GATE else "STOPS",
                    )
        else:
            cuedraw.console_preview(
                view,
                cues.console_preview(state, self.pending),
                devices,
                getattr(pyxel, "frame_count", 0),
                self.progress.settings.reduced_motion,
                self.layout.room,
            )

    def draw_ghosts(self, view, frame: preview.Frame, flicker: int) -> None:
        """The predicted echo, and the player's assumed spot when they differ."""
        ghosts = []
        if frame.echo is not None:
            ghosts.append((f"echo_idle_{flicker}", frame.echo))
        if frame.player != self.state.player:
            ghosts.append((f"player_idle_{flicker}", frame.player))
        for sprite, position in ghosts:
            pyxel.dither(0.5)
            self.sprite(sprite, position)
            pyxel.dither(1.0)
            pyxel.rectb(*cuedraw.tile(view, position), 12)

    def draw_bars(self) -> None:
        layout, state = self.layout, self.state
        scale = layout.text_scale
        edge = max(1, scale // 2)
        _, top_y, width, top_h = layout.top
        pyxel.rect(0, top_y, width, top_h, 1)
        pyxel.rect(0, top_y + top_h - edge, width, edge, 12)
        _, bottom_y, _, bottom_h = layout.bottom
        pyxel.rect(0, bottom_y, width, bottom_h, 1)
        pyxel.rect(0, bottom_y, width, edge, 5)
        actions = self.bar_actions()
        lesson = self.lesson.current if self.lesson is not None else None
        count = state.chamber.max_turns
        left = count - len(state.recording)
        hud = model(state)
        turn = self.preview_turn()
        # A running lesson keeps its instruction on the line unless something failed.
        speaks = self.message_frames and (lesson is None or self.message_error)
        shown = (
            self.preview_label(turn)
            if turn is not None
            else self.message
            if speaks
            else ""
        )
        counter = preview.expiry_text(state) or (
            f"TURNS LEFT {left}"
            if state.phase in (Phase.PREPARE, Phase.RECORDING)
            else f"RECORDED {len(state.recording)}/{count}"
        )
        items = bars.top_items(
            layout,
            hud,
            level=self.level,
            name=CHAMBER_NAMES[self.level - 1],
            step=next_step(actions, lesson.say("objective") if lesson else ""),
            feedback=shown,
            hints=f"HINTS {len(self.seen_hints)}/{len(self.hints)}",
            muted=self.muted,
        ) + bars.bottom_items(
            layout,
            hud,
            actions,
            count=count,
            counter=counter,
        )
        self.motion.sync_buttons(
            {item.key: item for item in items if item.kind == "button"}
        )
        for item in items:
            if item.key:
                self.ui_hits.append((item.rect, item.key))
            hidden = self.motion.button_hidden(item.key) if item.key else None
            if hidden is not None:
                self.draw_sliding(item, hud, hidden)
            else:
                self.draw_item(item, hud)
        for item, hidden in self.motion.leaving_buttons():
            self.draw_sliding(item, hud, hidden)  # no hit rect: it is gone

    def draw_sliding(self, item: bars.Item, hud: Hud, hidden: float) -> None:
        """A bar button part-way below the bar, clipped to it. Its hit rect stays
        where it will rest, so a click is never missed."""
        x, y, width, height = item.rect
        drop = round(hidden * (height + self.layout.pad))
        pyxel.clip(*self.layout.bottom)
        self.draw_item(replace(item, rect=(x, y + drop, width, height)), hud)
        pyxel.clip()

    def slot_done(self, index: int) -> bool:
        """Slots whose turn already happened in this replay."""
        state = self.state
        return (
            state.phase is Phase.REPLAY
            and index < len(state.recording)
            and index < preview.elapsed(state)
        )

    def preview_label(self, turn: int) -> str:
        frame = self.projection().at(turn)
        gone = "" if frame.echo is not None else " (ECHO HAS LEFT)"
        keys = " ".join(
            controls.find(self.play_actions(), i).key
            for i in ("preview_prev", "preview_next")
        )
        return f"PREVIEW TURN {turn}{gone}   {keys} CHANGE TURN   ANY OTHER KEY RETURNS"

    def introducing(self, key: str) -> bool:
        """Whether a bar button is a newly shown one, and its highlight is on now.

        The highlight blinks for a few seconds; with reduced motion it stays lit.
        """
        if not self.intro_frames or not key.startswith("action:"):
            return False
        if key.removeprefix("action:") not in controls.introduced(self.level):
            return False
        return (
            self.progress.settings.reduced_motion
            or motion.blink(self.intro_frames, 0.27) == 0
        )

    def draw_item(self, item: bars.Item, hud: Hud) -> None:
        layout = self.layout
        scale = layout.text_scale
        x, y, width, height = item.rect
        hover = bool(item.key) and self.menu_hit(item.rect)
        char = self.char_width(scale)
        text_y = y + (height - line_height(scale)) // 2
        text_x = x + layout.pad + item.lead
        if item.kind == "slot":
            index = int(item.key.removeprefix("timeline:"))
            self.atlas.draw(item.text, x, y, width, self.motion.pop(index))
            if item.cap:
                self.text(
                    x + (width - len(item.cap) * char) // 2,
                    y + (height - line_height(scale)) // 2,
                    item.cap,
                    13,
                )
            if item.on:
                pulse = 1 + PULSE_GROW * self.motion.pulse()
                self.atlas.draw("slot_current", x, y, width, pulse)
            if self.slot_done(index):
                pyxel.dither(0.5)
                pyxel.rect(x, y, width, height, 1)
                pyxel.dither(1.0)
                mark = max(2, width // 6)
                cx, cy = x + width - mark * 2, y + height - mark * 2
                pyxel.line(cx - mark, cy, cx - mark // 3, cy + mark // 2, 11)
                pyxel.line(cx - mark // 3, cy + mark // 2, cx + mark, cy - mark, 11)
            if self.preview_turn() == index + 1:
                pyxel.rectb(x, y, width, height, 12)
                pyxel.rectb(x + 1, y + 1, width - 2, height - 2, 12)
            if hover:
                pyxel.rectb(x, y, width, height, 10)
            return
        cap_color, color = 10, 7
        if item.kind == "button":
            if not item.enabled:
                cap_color = color = 13
            pyxel.rectb(
                x, y, width, height, (10 if hover else 12) if item.enabled else 5
            )
            if self.introducing(item.key):
                pyxel.rectb(x + 1, y + 1, width - 2, height - 2, 9)
                pyxel.rectb(x + 2, y + 2, width - 4, height - 4, 9)
        elif item.kind in ("power", "chip"):
            pyxel.rectb(x, y, width, height, 12 if hover else 5)
        if item.kind == "title":
            cap_color = 9
        elif item.kind == "chip":
            marker = max(4, 2 * scale + 2)
            pyxel.rect(
                x + layout.pad,
                y + (height - marker) // 2,
                marker,
                marker,
                11 if item.on else 8,
            )
            color = 7 if item.on else 13
        elif item.kind == "power":
            shown = self.motion.power_load(hud.load)
            span = width - 2 * layout.pad
            total = max(1.0, self.motion.capacity(hud.capacity))
            fill = round(span * min(shown, total) / total)
            # The track's tail is the capacity the energy cells added.
            own = round(span * min(hud.base, total) / total)
            pyxel.rect(text_x, y + height - 3, own, 1, 5)
            pyxel.rect(text_x + own, y + height - 3, span - own, 1, 10)
            pyxel.rect(text_x, y + height - 3, fill, 1, 11)
            if (swell := self.motion.capacity_pulse()) > 0:
                grow = round(swell * 2)
                pyxel.rectb(x - grow, y - grow, width + 2 * grow, height + 2 * grow, 10)
        elif item.kind == "safety":
            color = 11 if item.on else 8
        elif item.kind == "hints":
            color = 14
        elif item.kind == "muted":
            color = 13
        elif item.kind == "step" and item.on and self.flash:
            color = 8
        if item.cap:
            self.text(text_x, text_y, item.cap, cap_color)
            text_x += (len(item.cap) + 1) * char
        if item.text:
            self.text(text_x, text_y, item.text, color)

    def draw_panel(
        self,
        title: str,
        lines: list[str],
        footer: str,
        drawer: tuple[int, int, int, int] | None = None,
        rows: dict[int, str] | None = None,
        gap_units: int = 12,
        measure: list[str] | None = None,
    ) -> None:
        """Draw a card centred in the room, or fill `drawer` when one is given.

        `rows` maps line indexes to the "row:" keys that make those lines
        clickable; a hovered row gets an outline. `measure` sizes the card for
        those lines instead, so it does not grow as lines appear.
        """
        _, _, width, _ = drawer or self.layout.overlay()
        pad = max(18, self.layout.cell // 4)
        scale = 1 if self.layout.height < 600 else self.layout.text_scale
        footer_scale = scale
        footer_height = self.wrapped_height(footer, width - 2 * pad, footer_scale)
        while True:
            title_scale = max(2, scale + 1)
            title_height = self.wrapped_height(title, width - 2 * pad, title_scale)
            gap = gap_units * scale
            body_height = sum(
                self.wrapped_height(line, width - 2 * pad, scale) + gap
                for line in measure or lines
            )
            height = 2 * pad + title_height + body_height + footer_height + 36
            if (
                height <= (drawer[3] if drawer else self.layout.room_h - 16)
                or scale == 1
            ):
                break
            scale -= 1
        if drawer:
            x, y, _, height = drawer
        else:
            x = (self.layout.width - width) // 2
            y = self.layout.room_y + max(0, (self.layout.room_h - height) // 2)
            pyxel.rect(x + 6, y + 6, width, height, 5)
        pyxel.rect(x, y, width, height, 1)
        pyxel.rectb(x, y, width, height, 12)
        pyxel.rect(x, y, min(width // 5, pad * 4), max(3, self.layout.text_scale), 9)
        cursor = (
            self.wrapped(x + pad, y + pad, title, width - 2 * pad, 10, title_scale) + 6
        )
        pyxel.rect(x + pad, cursor, width - 2 * pad, max(1, self.layout.text_scale), 5)
        cursor += 14
        if self.modal == "lesson_choice":
            self.choice_hits = []
        for index, line in enumerate(lines):
            line_top = cursor
            accent = (
                8
                if line.startswith("OVER BUDGET")
                else 10
                if title == "POWER CONSOLE" and "*" in line
                else 7
            )
            cursor = (
                self.wrapped(x + pad, cursor, line, width - 2 * pad, accent, scale)
                + gap
            )
            if rows and index in rows:
                rect = (x + pad, line_top, width - 2 * pad, cursor - line_top)
                self.ui_hits.append((rect, "row:" + rows[index]))
                if self.menu_hit(rect):
                    pyxel.rectb(*rect, 10)
            if self.modal == "lesson_choice" and line.startswith(
                ("START GUIDED LESSON:", "PLAY FREELY:")
            ):
                rect = (
                    x + pad - 6,
                    line_top - 6,
                    width - 2 * pad + 12,
                    cursor - line_top,
                )
                self.choice_hits.append(rect)
                pyxel.rectb(
                    *rect,
                    10 if len(self.choice_hits) == 1 or self.menu_hit(rect) else 5,
                )
            if title == "POWER CONSOLE":
                for circuit in self.state.chamber.circuits:
                    if circuit.id.upper() in line and " UNIT" in line:
                        self.ui_hits.append(
                            (
                                (x + pad, line_top, width - 2 * pad, cursor - line_top),
                                "circuit:" + circuit.id,
                            )
                        )
                if line.startswith("PENDING LOAD"):
                    self.ui_hits.append(
                        (
                            (x + pad, line_top, width - 2 * pad, cursor - line_top),
                            "power",
                        )
                    )
        footer_y = y + height - pad - footer_height
        pyxel.rect(
            x + pad, footer_y - 11, width - 2 * pad, max(1, self.layout.text_scale), 5
        )
        self.wrapped(x + pad, footer_y, footer, width - 2 * pad, 12, footer_scale)

    def wrapped_height(self, value: str, width: int, scale: int) -> int:
        return len(
            textwrap.wrap(
                value,
                width=max(8, width // self.char_width(scale)),
                break_long_words=True,
                break_on_hyphens=False,
            )
        ) * self.line_height(scale)

    def draw_console(self) -> None:
        circuits = self.state.chamber.circuits
        configured = power.apply(
            self.state.chamber, self.pending, power.capacity_of(self.state)
        )
        pending_load = sum(c.load for c in circuits if c.id in self.pending)
        before = lighting.lit_tiles(self.state)
        after = lighting.lit_tiles(replace(self.state, powered_circuits=self.pending))
        dark = sorted(
            zone.id
            for zone in self.state.chamber.zones
            if any(tile in before and tile not in after for tile in zone.tiles)
        )
        keys = self.actions()
        lines = [
            controls.legend(
                keys, ("nav_prev", "nav_next", "toggle", "apply", "close")
            ).upper()
        ]
        if self.lesson is not None and self.lesson.current is not None:
            lines = [
                f"STEP {self.lesson.index + 1}/{len(self.lesson.steps)}: {self.lesson.current.say('objective')}"
            ] + lines
        rows = {
            len(lines) + index: "circuit:" + circuit.id
            for index, circuit in enumerate(circuits)
        }
        lines += [
            f"{'>' if index == self.selection else ' '} {'*' if self.lesson is not None and self.lesson.current is not None and self.lesson.current.target.get('id') == circuit.id else ' '} [{'X' if circuit.id in self.pending else ' '}] {circuit.id.upper()}  {circuit.load} UNIT{'' if circuit.load == 1 else 'S'}"
            for index, circuit in enumerate(circuits)
        ]
        lines += [f"PENDING LOAD {pending_load}/{power.capacity_of(self.state)}"]
        if not configured.ok:
            lines.append("OVER BUDGET - CANNOT APPLY")
        lines.append("WILL GO DARK: " + (", ".join(dark).upper() if dark else "NONE"))
        if live := sorted(
            conduit.id
            for conduit in self.state.chamber.conduits
            if conduit.circuit_id in self.pending
            and conduit.circuit_id not in self.state.powered_circuits
        ):
            lines.append("WILL GO LIVE: " + ", ".join(live).upper())
        rows[len(lines)] = "apply"
        lines.append(f"  {controls.cap('apply')} {controls.apply_label(self.state)}")
        x, y, width, height = self.layout.console_drawer()
        hidden = self.motion.drawer_hidden() or 0.0
        slid = round(hidden * width)
        marked = len(self.ui_hits)
        pyxel.clip(x + slid, y, width - slid, height)
        self.draw_panel(
            "POWER CONSOLE",
            lines,
            controls.legend(keys, ("undo", "guide", "hint")).upper(),
            (x + slid, y, width, height),
            rows,
        )
        pyxel.clip()
        # Rows stay clickable where the drawer rests; a closing drawer has none.
        self.ui_hits[marked:] = (
            [
                ((hx - slid, hy, hw, hh), key)
                for (hx, hy, hw, hh), key in self.ui_hits[marked:]
            ]
            if self.console
            else []
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
        pulse_x = px + (frame * 3 // 2) % max(1, pw - 65)
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
            tick = sy + frame % max(1, sh - step)
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
        bob = round(5 * math.sin(frame * math.tau / (3 * FPS)))
        sprite_size = self.layout.menu_rect(0, 0, 194, 0)[2]
        player_x, player_y, _, _ = self.layout.menu_rect(414, 351, 0, 0)
        echo_x, echo_y, _, _ = self.layout.menu_rect(677, 351, 0, 0)
        self.atlas.draw(
            f"player_idle_{motion.blink(frame, 0.5)}",
            player_x,
            player_y + bob,
            sprite_size,
        )
        self.atlas.draw(
            f"echo_idle_{motion.blink(frame, 0.5)}", echo_x, echo_y - bob, sprite_size
        )
        button = self.layout.start_button()
        x, y, width, height = button
        hovered = self.mouse_active and self.menu_hit(button)
        pulse = motion.blink(frame, 0.6) == 0
        pyxel.rect(x, y, width, height, 5 if hovered else 1)
        pyxel.rectb(x, y, width, height, 10 if hovered or pulse else 9)
        accent = max(2, self.layout.text_scale)
        pyxel.rect(x + accent, y + accent, max(12, width // 5), accent, 12)
        key = controls.cap("confirm").upper()
        label = f"{key} / CLICK" if width < 250 else f"CLICK OR {key} TO START"
        text_scale = max(1, self.layout.text_scale + 1)
        self.text(
            x + (width - len(label) * 4 * text_scale) // 2,
            y + (height - 7 * text_scale) // 2,
            label,
            10,
            text_scale,
        )
        footer_y = self.layout.menu_rect(0, 631, 0, 0)[1]
        self.centered(
            footer_y,
            controls.legend(self.actions(), ("mute", "fullscreen")).upper(),
            13,
        )
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
            color = (
                10
                if selected and motion.blink(frame, 0.6) == 0
                else 12
                if selected
                else 6
            )
            if not unlocked:
                color = 5 if not selected else 13
            pyxel.rect(x, y, width, height, 1)
            pyxel.rectb(x, y, width, height, color)
            inset = max(3, self.layout.text_scale * 2)
            pyxel.rectb(x + inset, y + inset, width - 2 * inset, height - 2 * inset, 5)
            if selected or hovered:
                bar = max(15, width // 5)
                travel = max(1, width - 2 * inset - bar)
                pyxel.rect(x + inset + frame % travel, y + inset, bar, inset, color)
            number_scale = max(2, self.layout.text_scale + 4)
            self.text(
                x + inset * 3,
                y + inset * 4,
                f"{number:02}",
                9 if unlocked else 13,
                number_scale,
            )
            if unlocked:
                self.draw_marks(x + width - inset * 3, y + inset * 4, number)
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
            controls.legend(
                self.actions(), ("nav_prev", "confirm", "close", "fullscreen")
            ).upper(),
        )
        self.draw_cursor()

    def draw_marks(self, right: int, top: int, number: int) -> None:
        """Draw the card's marks (C, T, R) right-aligned: filled when earned."""
        scale = max(1, self.layout.text_scale)
        size = 7 * scale + 4
        shown = goals.marks(self.progress, number, self.goal_targets)
        x = right - len(shown) * size - (len(shown) - 1) * 2
        for letter, earned in shown:
            if earned:
                pyxel.rect(x, top, size, size, 11)
            pyxel.rectb(x, top, size, size, 11 if earned else 5)
            self.text(x + 2 + scale, top + 2, letter, 1 if earned else 13, scale)
            x += size + 2

    def line_height(self, scale: int) -> int:
        return line_height(scale)

    def draw_lesson_card(self) -> None:
        self.lesson_card_rect = (0, 0, 0, 0)
        if self.lesson is None or self.lesson.current is None:
            return
        step = self.lesson.current
        target = step.target
        cell, ox, oy = self.room_view
        if target["kind"] == "tile":
            tx, ty = target["position"]
            px, py = ox + tx * cell, oy + ty * cell
            pyxel.clip(*self.layout.room)
            for inset in (2, 4):
                pyxel.rectb(
                    px + inset, py + inset, cell - 2 * inset, cell - 2 * inset, 10
                )
            cuedraw.offscreen(
                self.room_view,
                self.layout.room_viewport(self.console),
                (("target", (tx, ty)),),
            )
            pyxel.clip()
        elif target["kind"] in {"power", "state", "timeline"}:
            topic = (
                f"timeline:{target['index']}"
                if target["kind"] == "timeline"
                else target["kind"]
            )
            for rect, key in self.ui_hits:
                if key == topic:
                    pyxel.rectb(*rect, 10)
        self.lesson_card_rect = (0, 0, 0, 0)
        if not self.lesson.card_open:
            return  # The Next step line carries the instruction.
        x, y = self.layout.room_x + 12, self.layout.room_y + 12
        beside = self.layout.drawer_width + self.layout.pad if self.console else 0
        width = self.layout.room_w - beside - 24
        scale = 1 if self.layout.width < 900 else 2
        heading = step.say("title").upper()
        body = step.say("explanation")
        footer = (
            f"{controls.cap('apply')} OR CLICK TO CLOSE, OR JUST DO THE STEP".upper()
        )
        chars = max(8, (width - 24) // self.char_width(scale))
        rows = sum(len(textwrap.wrap(text, chars)) for text in (heading, body, footer))
        height = rows * self.line_height(scale) + 44
        self.lesson_card_rect = (x, y, width, height)
        pyxel.rect(x, y, width, height, 1)
        pyxel.rectb(
            x, y, width, height, 10 if self.menu_hit((x, y, width, height)) else 12
        )
        cy = self.wrapped(x + 12, y + 12, heading, width - 24, 10, scale) + 8
        cy = self.wrapped(x + 12, cy, body, width - 24, 7, scale) + 8
        self.wrapped(x + 12, cy, footer, width - 24, 6, scale)

    def hovered_topic(self) -> tuple[str, str] | None:
        for rect, key in reversed(self.ui_hits):
            if self.menu_hit(rect):
                if key.startswith("action:"):
                    action = controls.find(self.play_actions(), key[7:])
                    return action.label.upper(), action.reason or (
                        f"Press {action.key} or click." if action.key else "Click."
                    )
                for topic_key, title, detail in topics(
                    self.state, self.pending, self.console, self.terminals
                ):
                    if key == topic_key:
                        return title, detail
        if self.console or (
            self.lesson is not None and self.menu_hit(self.lesson_card_rect)
        ):
            return None
        position = self.pointer_tile(self.shaken)
        if position is None:
            return None
        return room_info(self.state, position, terminals=self.terminals)

    def draw_hover(self) -> None:
        topic = self.hovered_topic()
        if topic is None:
            return
        title, detail = topic
        width = min(560, self.layout.room_w - 24)
        scale = 1
        chars = max(8, (width - 24) // self.char_width(scale))
        height = (
            len(textwrap.wrap(detail, chars, break_on_hyphens=False))
            + len(textwrap.wrap(title, chars))
        ) * self.line_height(scale) + 36
        x = self.layout.room_x + 12
        y = self.layout.room_y + self.layout.room_h - height - 12
        pyxel.rect(x, y, width, height, 1)
        pyxel.rectb(x, y, width, height, 12)
        cy = self.wrapped(x + 12, y + 10, title, width - 24, 10, scale) + 8
        self.wrapped(x + 12, cy, detail, width - 24, 7, scale)

    def draw_modal(self) -> None:
        keys = self.actions()
        if self.modal == "lesson_choice":
            self.draw_panel(
                f"CHAMBER {self.level:02} / LEARN TO PLAY",
                [
                    "START GUIDED LESSON: step-by-step explanations with checked actions.",
                    f"PLAY FREELY: solve the chamber on your own. {controls.key_text('guide')} opens the guide and {controls.key_text('hint')} reveals a hint.",
                ],
                controls.legend(keys, ("confirm", "free_play")).upper(),
            )
        elif self.modal == "guide":
            self.draw_guide()
        elif self.modal == "log":
            self.draw_log()
        elif self.modal == "result":
            ids = (
                ("confirm", "close", "restart")
                if self.level < LEVEL_COUNT
                else ("close", "restart")
            )
            lines = [
                self.lesson_summary
                if self.lesson is not None
                else "You reached the running elevator. Choose a guided lesson on your next visit to review each mechanic.",
                *(self.run.lines() if self.run else ()),
                f"HINTS USED: {len(self.seen_hints)}",
            ]
            self.draw_panel(
                f"CHAMBER {self.level} COMPLETE",
                lines + self.menu_lines(ids),
                "",
                rows={len(lines) + i: "result:" + a for i, a in enumerate(ids)},
            )

    def draw_log(self) -> None:
        """The log card: lines appear one at a time in a card sized for them all."""
        lines = list(self.log.lines)
        last = self.log_page >= len(lines)
        keys = self.actions()
        footer = (
            f"{controls.cap('confirm')} {controls.find(keys, 'close').label}"
            if last
            else controls.legend(keys, ("confirm", "close"))
        )
        self.draw_panel(
            f"LOG TERMINAL / {min(self.log_page, len(lines))}/{len(lines)}",
            lines[: self.log_page],
            footer.upper(),
            measure=lines,
        )

    def menu_lines(self, action_ids: tuple[str, ...], selected: int = -1) -> list[str]:
        keys = {action.id: action for action in self.actions()}
        lines = []
        for index, action_id in enumerate(action_ids):
            action = keys[action_id]
            cap = f"{action.key} " if action.key else ""
            note = "" if action.enabled else f" - {action.reason}"
            marker = ">" if index == selected else " "
            lines.append(f"{marker} {cap}{action.label}{note}")
        return lines

    def draw_pause(self) -> None:
        if self.settings_open:
            self.draw_settings()
            return
        keys = self.actions()
        self.draw_panel(
            "PAUSED",
            self.menu_lines(PAUSE_ITEMS, self.pause_index),
            controls.legend(
                keys, ("nav_prev", "nav_next", "confirm", "fullscreen")
            ).upper(),
            rows={i: "pause:" + a for i, a in enumerate(PAUSE_ITEMS)},
        )

    def draw_settings(self) -> None:
        keys = {action.id: action for action in self.actions()}
        lines = []
        for index, item in enumerate(SETTINGS_ITEMS):
            marker = ">" if index == self.settings_index else " "
            label = keys[item].label
            if item == "close":
                lines.append(f"{marker} {label}")
            else:
                lines.append(f"{marker} {label}: {self.settings_value(item)}")
        self.draw_panel(
            "SETTINGS",
            lines,
            controls.legend(
                list(keys.values()),
                ("row_prev", "row_next", "value_down", "value_up", "close"),
            ).upper(),
            rows={i: "setting:" + item for i, item in enumerate(SETTINGS_ITEMS)},
        )

    def draw_guide(self) -> None:
        page = guide.PAGE_IDS[self.guide_page]
        names = [
            f"[{name}]" if i == self.guide_page else name
            for i, (_, name) in enumerate(guide.PAGES)
        ]
        lines = [" ".join(names)]
        lines += guide.page_lines(
            page,
            self.state,
            level=self.level,
            revealed=self.hints[: self.hint_index],
            total_hints=len(self.hints),
            terminals=self.terminals,
        )
        count = len(guide.PAGES)
        previous = guide.PAGES[(self.guide_page - 1) % count][1]
        following = guide.PAGES[(self.guide_page + 1) % count][1]
        keys = self.actions()
        rows = {
            len(lines): "guide:prev",
            len(lines) + 1: "guide:next",
            len(lines) + 2: "guide:close",
        }
        lines += [
            f"< {controls.find(keys, 'nav_prev').label}: {previous}",
            f"> {controls.find(keys, 'nav_next').label}: {following}",
            controls.find(keys, "close").label,
        ]
        self.draw_panel(
            f"GUIDE {self.guide_page + 1}/{count} / {guide.title(page)}",
            lines,
            controls.legend(keys, ("nav_prev", "nav_next", "hint", "close")).upper(),
            rows=rows,
            gap_units=5,
        )

    def draw_failure(self) -> None:
        keys = self.actions()
        retry = controls.find(keys, "retry")
        self.draw_panel(
            "ATTEMPT FAILED",
            [self.failure.reason.capitalize()]
            + self.menu_lines(("undo", "retry", "restart"), 1 if retry.enabled else -1),
            "ANY OTHER KEY: "
            + (retry.label if retry.enabled else "START AGAIN").upper(),
            rows={
                1: "failure:undo",
                2: "failure:retry",
                3: "failure:restart",
            },
        )

    def draw(self) -> None:
        self.sync_mouse()
        pyxel.cls(1)
        self.draw_screen()
        if cover := self.motion.fade():
            cuedraw.fade(self.layout.width, self.layout.height, cover)

    def draw_screen(self) -> None:
        if self.mode == "title":
            self.draw_title()
            return
        if self.mode == "levels":
            self.draw_levels()
            return
        self.ui_hits = []
        self.draw_room()
        self.draw_bars()
        self.draw_lesson_card()
        if self.console or self.motion.drawer_hidden() is not None:
            self.draw_console()
        if self.failure is not None:
            self.draw_failure()
        if self.paused:
            self.draw_pause()
        if self.modal and not self.paused and self.failure is None:
            self.draw_modal()
        if not self.modal and not self.paused and self.failure is None:
            self.draw_hover()
        self.draw_cursor()


def main() -> None:
    game = Game()
    pyxel.run(game.update, game.draw)
