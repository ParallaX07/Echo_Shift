"""Pyxel input and rendering for the prototype chamber."""

import json
import logging
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
from echo_shift.ui.hud import model

CELL = 32
logger = logging.getLogger(__name__)
ROOM_H = 288
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
        pyxel.init(384, 352, title="Echo Shift - Prototype", fps=30)
        (user_data_dir() / "startup.log").write_text("Echo Shift prototype started\n")
        self.atlas = Atlas()
        self.state = initial_state(load(resource_path("levels", "chamber_proto.json")))
        self.paused = False
        self.console = False
        self.selection = 0
        self.pending = self.state.powered_circuits
        self.message = "E POWER  ENTER RECORD  Q LAUNCH"
        self.message_frames = 120
        self.flash = 0

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
            logger.warning("%s reason=%s", details, result.reason)
            self.notice(f"FAILED: {result.reason}  R RETRY", True)
        else:
            logger.info("%s", details)
            if result.succeeded:
                self.notice("ELEVATOR REACHED!  C RESTART")

    def update(self) -> None:
        self.message_frames = max(0, self.message_frames - 1)
        self.flash = max(0, self.flash - 1)
        if pyxel.btnp(pyxel.KEY_P):
            self.paused = not self.paused
        if self.paused:
            if pyxel.btnp(pyxel.KEY_C):
                self.state = recording.clear(self.state)
                self.paused = False
                self.notice("CHAMBER CLEARED")
            return
        if self.console:
            self.console_input()
            return
        if pyxel.btnp(pyxel.KEY_C):
            self.state = recording.clear(self.state)
            self.notice("CHAMBER CLEARED")
        elif pyxel.btnp(pyxel.KEY_R):
            self.state = recording.retry(self.state)
            self.notice("RETRY FROM LAUNCH")
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
                self.notice("OVER BUDGET - REMOVE A CIRCUIT", True)
            elif self.pending == self.state.powered_circuits:
                self.console = False
            else:
                self.act(InteractAtConsole(self.pending))
                self.console = False

    def sprite(self, name: str, pos: Position) -> None:
        self.atlas.draw(name, pos.x * CELL, pos.y * CELL)

    def draw_room(self) -> None:
        state = self.state
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
                    pyxel.text(x * CELL + 2, y * CELL + 2, "A", 7)
        if state.echo_position is not None:
            self.sprite("echo_idle_0", state.echo_position)
        self.sprite("player_idle_0", state.player)
        if self.flash and self.flash % 4 < 2:
            pyxel.rectb(0, 0, 384, ROOM_H, 8)

    def draw_hud(self) -> None:
        info = model(self.state)
        pyxel.rect(0, ROOM_H, 384, 64, 1)
        pyxel.rect(0, ROOM_H, 384, 1, 6)
        pyxel.text(4, 293, f"POWER {info.load}/{info.capacity}", 7)
        pyxel.rectb(76, 292, 102, 7, 6)
        pyxel.rect(77, 293, round(100 * info.load / max(1, info.capacity)), 5, 11)
        pyxel.text(185, 293, "SAFE" if info.safe else "DARK", 11 if info.safe else 8)
        summary = " ".join(
            f"{name[:3].upper()}:{'ON' if on else 'OFF'}" for name, on in info.circuits
        )
        pyxel.text(233, 293, summary[:24], 7)
        pyxel.text(
            4,
            306,
            (self.message if self.message_frames else self.state.phase.value.upper())[
                :62
            ],
            8 if self.flash else 7,
        )
        for index, (kind, current, direction) in enumerate(info.timeline):
            x = index * 32
            self.atlas.draw("slot_" + kind, x, 320)
            if direction:
                pyxel.text(x + 14, 342, direction, 7)
            if current:
                pyxel.rectb(x, 320, 32, 32, 12)
            if index >= self.state.chamber.max_turns:
                pyxel.rectb(x, 320, 32, 32, 5)

    def draw_console(self) -> None:
        pyxel.rect(42, 45, 300, 197, 1)
        pyxel.rectb(42, 45, 300, 197, 12)
        pyxel.text(56, 56, "POWER CONSOLE", 10)
        pyxel.text(56, 68, "UP/DOWN SELECT  SPACE TOGGLE  ENTER APPLY  E EXIT", 7)
        for index, circuit in enumerate(self.state.chamber.circuits):
            y = 89 + index * 21
            selected = circuit.id in self.pending
            pyxel.text(58, y, ">" if index == self.selection else " ", 10)
            pyxel.text(
                69,
                y,
                f"[{'X' if selected else ' '}] {circuit.id.upper()}  {circuit.load} UNITS",
                11 if selected else 7,
            )
        configured = power.apply(self.state.chamber, self.pending)
        pending_load = sum(
            c.load for c in self.state.chamber.circuits if c.id in self.pending
        )
        pyxel.text(
            56,
            144,
            f"PENDING LOAD {pending_load}/{self.state.chamber.capacity}",
            11 if configured.ok else 8,
        )
        if not configured.ok:
            pyxel.text(56, 156, "OVER BUDGET - CANNOT APPLY", 8)
        before = lighting.lit_tiles(self.state)
        after = lighting.lit_tiles(replace(self.state, powered_circuits=self.pending))
        dark = sorted(
            zone.id
            for zone in self.state.chamber.zones
            if any(tile in before and tile not in after for tile in zone.tiles)
        )
        pyxel.text(
            56,
            177,
            "WILL GO DARK: " + (", ".join(dark).upper() if dark else "NONE"),
            8 if dark else 11,
        )
        pyxel.text(56, 201, "Record pad route with LAB on. Then power LIFT.", 7)

    def draw(self) -> None:
        pyxel.cls(1)
        self.draw_room()
        self.draw_hud()
        if self.console:
            self.draw_console()
        if self.paused:
            pyxel.rect(90, 106, 204, 72, 1)
            pyxel.rectb(90, 106, 204, 72, 12)
            pyxel.text(155, 126, "PAUSED", 7)
            pyxel.text(119, 147, "P RESUME    C CLEAR", 7)


def main() -> None:
    game = Game()
    pyxel.run(game.update, game.draw)
