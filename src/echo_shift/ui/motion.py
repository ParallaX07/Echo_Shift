"""Code-driven motion: pure timelines plus the `Motion` object that holds them.

Nothing here imports Pyxel or changes the rules. The engine steps at once on
input; the renderer then eases from the previous state to the new one. Every
timeline is a pure function of the frames elapsed, starts at what the previous
state showed and ends exactly on what the new state shows. Lengths are in Pyxel
frames at a fixed 60 per second. New input calls `Motion.snap`, which jumps every
running timeline to its end, so animation never queues, delays or swallows a turn.
With reduced motion no timeline is ever started: the end frame shows at once.
"""

import math
from dataclasses import dataclass
from typing import NamedTuple

from echo_shift.engine import lighting, power
from echo_shift.engine.model import Phase, Position, State
from echo_shift.engine.turn import Failed

FPS = 60

WALK_FRAMES = 15  # player or echo gliding one tile, steadily
STRIDE_FRAMES = 5  # frames per step sprite while gliding
NUDGE_FRAMES = 8  # a refused move: out and back
NUDGE_DISTANCE = 0.2  # of a tile
SPAWN_FRAMES = 12  # echo_spawn_0..2, then the idle sprite
EXPIRE_FRAMES = 12  # echo_expire_0..2, then nothing
GATE_FRAMES = 12  # gate_closed, gate_mid, gate_open (or back)
ELEVATOR_FRAMES = 24  # elevator_off, then elevator_on / elevator_on_1 pulses
PAD_PRESS_FRAMES = 8  # pad_off, pad_press, pad_on (or back)
PAD_GLOW_FRAMES = 15  # pad_timed_off, pad_timed_glow_0..2, pad_timed_on (or back)
TICK_FRAMES = 10  # a timed pad's countdown number hops once per turn
TICK_LIFT = 0.08  # of a tile
LIGHT_FRAMES = 12  # tiles fading between lit and dark
SHAKE_FRAMES = 18  # failure screen shake
SHAKE_AMPLITUDE = 0.06  # of a tile, fading to nothing
VIGNETTE_FRAMES = 30  # red edge after a failure
BURST_FRAMES = 36  # chamber-clear sparks
BURST_COUNT = 12
BURST_RADIUS = 1.2  # tiles
BURST_COLOURS = (10, 9, 7, 11)
SPARKLE_FRAMES = 24  # a picked-up energy cell's sparks
SPARKLE_COUNT = 8
SPARKLE_RADIUS = 0.7  # tiles
SPARKLE_COLOURS = (10, 7, 9)
CAPACITY_FRAMES = 30  # the power bar easing to a new capacity, and pulsing
FADE_FRAMES = 18  # a new screen fading in from the background colour
UNDO_PACE = 2  # an undo replays the step it undoes backwards, this much faster
POP_FRAMES = 8  # a timeline slot growing and settling as it is filled
POP_GROW = 0.3  # extra size of a slot at the top of its pop
POWER_FRAMES = 12  # the power bar easing to a new load
DRAWER_FRAMES = 10  # the console drawer sliding in or out
BUTTON_FRAMES = 10  # a bottom-bar button sliding in or out
PULSE_FRAMES = 36  # the playback slot swelling once
PULSE_GROW = 0.12
BREATH_SECONDS = 0.8  # the idle bob switches this often
SPRITE_PX = 96  # sprites are this many pixels tall; the bob is one of them
FLICKER_PERIOD = 150  # the hub console screen flickers once per period
FLICKER_FRAMES = 4  # ... for this many frames (well under 3 flashes a second)
CONDUIT_FRAMES = 180  # a pulse crossing the powered conduit rails
TRAIL_LENGTH = 3  # echo positions kept for its ghost trail
TRAIL_ALPHA = (0.5, 0.3, 0.15)  # dither strength of each trail ghost, newest first
DUST_COUNT = 6
DUST_LIFE = 180  # frames a mote drifts before it is replaced elsewhere
DUST_COLOURS = (5, 6, 13)

LENGTHS = {
    "slide": WALK_FRAMES,
    "nudge": NUDGE_FRAMES,
    "spawn": SPAWN_FRAMES,
    "expire": EXPIRE_FRAMES,
    "gate": GATE_FRAMES,
    "elevator": ELEVATOR_FRAMES,
    "pad": PAD_PRESS_FRAMES,
    "glow": PAD_GLOW_FRAMES,
    "tick": TICK_FRAMES,
    "light": LIGHT_FRAMES,
    "shake": SHAKE_FRAMES,
    "vignette": VIGNETTE_FRAMES,
    "burst": BURST_FRAMES,
    "fade": FADE_FRAMES,
    "sparkle": SPARKLE_FRAMES,
    "capacity": CAPACITY_FRAMES,
    "pop": POP_FRAMES,
    "power": POWER_FRAMES,
    "drawer": DRAWER_FRAMES,
    "button": BUTTON_FRAMES,
}


class Particle(NamedTuple):
    """A clear spark: offset from the burst centre and its size, in tiles."""

    dx: float
    dy: float
    size: float
    colour: int


def blink(frame: int, seconds: float) -> int:
    """0 or 1, flipping every `seconds` of a running frame counter."""
    return frame // max(1, round(seconds * FPS)) % 2


def progress(elapsed: int, length: int) -> float:
    """How far a timeline is, 0.0 to 1.0 (exactly 1.0 from `length` on)."""
    return min(1.0, max(0.0, elapsed / length))


def ease_out(p: float) -> float:
    return 1.0 - (1.0 - p) * (1.0 - p)


def ease_in_out(p: float) -> float:
    return p * p * (3.0 - 2.0 * p)


def hump(p: float) -> float:
    """0 at both ends, 1 in the middle; exactly 0 at p = 0 and p = 1."""
    return ease_in_out(1.0 - abs(2.0 * p - 1.0))


def stage(stages: tuple, elapsed: int, length: int):
    """The entry of `stages` on show: the first at 0, the last from `length` on."""
    if elapsed >= length:
        return stages[-1]
    return stages[max(0, elapsed) * len(stages) // length]


def slide(a: Position, b: Position, elapsed: int) -> tuple[float, float]:
    """Tile coordinates between `a` and `b`, an even glide: exactly `a` at 0 and
    `b` from `WALK_FRAMES` on."""
    p = progress(elapsed, WALK_FRAMES)
    return a.x + (b.x - a.x) * p, a.y + (b.y - a.y) * p


def walk_sprite(prefix: str, elapsed: int) -> str:
    """`<prefix>_step_0` and `_1` alternating every `STRIDE_FRAMES` of a glide."""
    return f"{prefix}_step_{max(0, elapsed) // STRIDE_FRAMES % 2}"


def nudge(direction: tuple[int, int], elapsed: int) -> tuple[float, float]:
    """Offset in tiles for a move that was refused: lean towards it and return."""
    amount = NUDGE_DISTANCE * hump(progress(elapsed, NUDGE_FRAMES))
    return direction[0] * amount, direction[1] * amount


def spawn_sprite(elapsed: int) -> str | None:
    """The echo appearing; None once it is whole (the idle sprite takes over)."""
    if elapsed >= SPAWN_FRAMES:
        return None
    return stage(
        ("echo_spawn_0", "echo_spawn_1", "echo_spawn_2"), elapsed, SPAWN_FRAMES
    )


def expire_sprite(elapsed: int) -> str | None:
    """The echo dissolving; None once it is gone."""
    if elapsed >= EXPIRE_FRAMES:
        return None
    return stage(
        ("echo_expire_0", "echo_expire_1", "echo_expire_2"), elapsed, EXPIRE_FRAMES
    )


def gate_sprite(opening: bool, elapsed: int) -> str:
    bars = ("gate_closed", "gate_mid", "gate_open")
    return stage(bars if opening else bars[::-1], elapsed, GATE_FRAMES)


def elevator_sprite(elapsed: int) -> str:
    on = ("elevator_on", "elevator_on_1")
    stages = ("elevator_off", on[0], on[1], on[0], on[1], on[0])
    return stage(stages, elapsed, ELEVATOR_FRAMES)


def pad_sprite(active: bool, timed: bool, elapsed: int) -> str:
    """A pad being pressed (or released); timed pads ramp a glow instead."""
    if timed:
        glow = (
            "pad_timed_off",
            "pad_timed_glow_0",
            "pad_timed_glow_1",
            "pad_timed_glow_2",
            "pad_timed_on",
        )
        return stage(glow if active else glow[::-1], elapsed, PAD_GLOW_FRAMES)
    press = ("pad_off", "pad_press", "pad_on")
    return stage(press if active else press[::-1], elapsed, PAD_PRESS_FRAMES)


def tick_lift(elapsed: int) -> float:
    """How far (in tiles) a countdown number is lifted as the timer ticks."""
    return TICK_LIFT * hump(progress(elapsed, TICK_FRAMES))


def light_progress(elapsed: int) -> float:
    """0 = how the tile looked before, 1 = how it looks now."""
    return ease_in_out(progress(elapsed, LIGHT_FRAMES))


def shake(elapsed: int) -> tuple[float, float]:
    """Screen offset in tiles: a fast wobble that dies away to exactly (0, 0)."""
    if elapsed >= SHAKE_FRAMES:
        return 0.0, 0.0
    left = 1.0 - progress(elapsed, SHAKE_FRAMES)
    amount = SHAKE_AMPLITUDE * left
    return (
        amount * (1 if elapsed // 2 % 2 == 0 else -1),
        amount * 0.5 * (1 if (elapsed + 1) // 3 % 2 == 0 else -1),
    )


def vignette(elapsed: int) -> float:
    """Strength 0..1 of the red edge: a quick rise, then a slower fall to 0."""
    p = progress(elapsed, VIGNETTE_FRAMES)
    return p / 0.2 if p < 0.2 else (1.0 - p) / 0.8


def burst(elapsed: int) -> tuple[Particle, ...]:
    """Sparks flying out from the exit; empty once the burst is over."""
    if elapsed >= BURST_FRAMES:
        return ()
    p = progress(elapsed, BURST_FRAMES)
    reach = ease_out(p) * BURST_RADIUS
    return tuple(
        Particle(
            math.cos(i * math.tau / BURST_COUNT) * reach,
            math.sin(i * math.tau / BURST_COUNT) * reach,
            0.12 * (1.0 - p),
            BURST_COLOURS[i % len(BURST_COLOURS)],
        )
        for i in range(BURST_COUNT)
    )


def sparkle(elapsed: int) -> tuple[Particle, ...]:
    """Small sparks rising off a cell that was just picked up; empty when over."""
    if elapsed >= SPARKLE_FRAMES:
        return ()
    p = progress(elapsed, SPARKLE_FRAMES)
    reach = ease_out(p) * SPARKLE_RADIUS
    return tuple(
        Particle(
            math.cos(i * math.tau / SPARKLE_COUNT) * reach,
            math.sin(i * math.tau / SPARKLE_COUNT) * reach - 0.3 * p,
            0.1 * (1.0 - p),
            SPARKLE_COLOURS[i % len(SPARKLE_COLOURS)],
        )
        for i in range(SPARKLE_COUNT)
    )


def capacity_pulse(elapsed: int) -> float:
    """0..1 swelling of the capacity bar's frame after it grew; 0 at both ends."""
    return hump(progress(elapsed, CAPACITY_FRAMES))


def fade_alpha(elapsed: int) -> float:
    """Cover of the background colour 1.0 -> 0.0 as a screen fades in."""
    return 1.0 - ease_in_out(progress(elapsed, FADE_FRAMES))


def pop_scale(elapsed: int) -> float:
    """Size factor of a slot just filled: 1 at both ends, swelling in between."""
    return 1.0 + POP_GROW * hump(progress(elapsed, POP_FRAMES))


def eased_load(was: int, now: int, elapsed: int) -> float:
    """The power bar's load while it eases from `was` to exactly `now`."""
    return was + (now - was) * ease_out(progress(elapsed, POWER_FRAMES))


def drawer_hidden(opening: bool, elapsed: int) -> float:
    """How much of the console drawer is still off screen: 1 hidden, 0 in place."""
    p = progress(elapsed, DRAWER_FRAMES)
    return 1.0 - ease_out(p) if opening else ease_in_out(p)


def button_hidden(appearing: bool, elapsed: int) -> float:
    """How much of a bar button is still below the bar: 1 hidden, 0 in place."""
    p = progress(elapsed, BUTTON_FRAMES)
    return 1.0 - ease_out(p) if appearing else ease_in_out(p)


def breath(frame: int, offset: int = 0) -> float:
    """How far a resting figure is lifted, in tiles: one sprite pixel, then none."""
    return blink(frame + offset, BREATH_SECONDS) / SPRITE_PX


def pulse(frame: int) -> float:
    """0..1 swelling of the playback slot, repeating every `PULSE_FRAMES`."""
    return hump(progress(frame % PULSE_FRAMES, PULSE_FRAMES))


def console_lit(frame: int) -> bool:
    """Whether the hub console shows its flicker frame."""
    return frame % FLICKER_PERIOD < FLICKER_FRAMES


def conduit(frame: int) -> float:
    """How far (0..1) a pulse has travelled along the conduit rails."""
    return frame % CONDUIT_FRAMES / CONDUIT_FRAMES


class Mote(NamedTuple):
    """A dust mote: which lit tile (a number to take modulo), where in it, colour."""

    pick: int
    x: float
    y: float
    colour: int


def _scatter(seed: int) -> int:
    return (seed * 1103515245 + 12345) & 0x7FFFFFFF


def dust(frame: int) -> tuple[Mote, ...]:
    """The motes on show at `frame`: a fixed pseudo-random drift, the same every
    run. Each rises slowly and is absent while it would pop in or out."""
    motes = []
    for i in range(DUST_COUNT):
        cycle, age = divmod(frame + i * DUST_LIFE // DUST_COUNT, DUST_LIFE)
        if age < 12 or age >= DUST_LIFE - 12:
            continue
        r = _scatter(_scatter(i * 7919 + cycle))
        motes.append(
            Mote(
                r >> 4,
                (r >> 8 & 255) / 255,
                0.2 + 0.7 * (r >> 16 & 255) / 255 - 0.15 * age / DUST_LIFE,
                DUST_COLOURS[(r >> 24) % len(DUST_COLOURS)],
            )
        )
    return tuple(motes)


class Walker:
    """Hold-to-walk: a held direction steps again exactly as the last glide lands.

    A fresh press always steps at once (the caller does that). While the key stays
    down, `repeats` is true once `WALK_FRAMES` have passed since the last step, so
    the next glide starts the frame the previous one ends. A step that went
    nowhere, a disabled move (a full recording) or a release ends the walk.
    The count does not depend on whether glides are drawn."""

    def __init__(self) -> None:
        self.action: str | None = None
        self.wait = 0

    def stepped(self, action_id: str, moved: bool) -> None:
        self.action = action_id if moved else None
        self.wait = WALK_FRAMES

    def stop(self) -> None:
        self.action = None

    def tick(self, played: bool) -> None:
        """Once per frame, after input; `played` is whether play input ran."""
        if not played:
            self.stop()
        self.wait = max(0, self.wait - 1)

    def repeats(self, action_id: str, held: bool, allowed: bool) -> bool:
        if self.action != action_id:
            return False
        if not (held and allowed):
            self.stop()
            return False
        return self.wait == 0


def _near(a: Position, b: Position) -> bool:
    return abs(a.x - b.x) + abs(a.y - b.y) == 1


def _load(state: State) -> int:
    return sum(c.load for c in state.chamber.circuits if c.id in state.powered_circuits)


@dataclass(frozen=True)
class Effect:
    start: int
    params: tuple = ()
    pace: int = 1  # elapsed frames counted per real frame (an undo runs at double)


class Motion:
    """The running timelines. `start` builds them from a state difference, `tick`
    advances one frame, `snap` ends them all, and the queries say what to draw."""

    def __init__(self, reduced: bool = False) -> None:
        self.reduced = reduced
        self.clock = 0
        self._effects: dict[tuple[str, object], Effect] = {}
        self._pace = 1
        self._trail: list[Position] = []
        self._drawer_open = False
        self._buttons: dict[str, object] | None = None

    @property
    def running(self) -> bool:
        return bool(self._effects)

    def set_reduced(self, reduced: bool) -> None:
        if reduced:
            self.snap()
            self.forget()
        self.reduced = reduced

    def tick(self) -> None:
        self.clock += 1
        self._effects = {
            key: effect
            for key, effect in self._effects.items()
            if (self.clock - effect.start) * effect.pace < LENGTHS[key[0]]
        }

    def snap(self) -> None:
        """Jump every timeline to its end: the screen shows the new state."""
        self._effects = {}

    def forget(self) -> None:
        """Drop the echo's ghost trail (a new run, a restore or a new screen)."""
        self._trail = []

    def _add(self, kind: str, key: object = None, *params: object) -> None:
        self._effects[kind, key] = Effect(self.clock, params, self._pace)

    def _get(self, kind: str, key: object = None) -> tuple[int, tuple] | None:
        effect = None if self.reduced else self._effects.get((kind, key))
        if effect is None:
            return None
        return (self.clock - effect.start) * effect.pace, effect.params

    def fade_in(self) -> None:
        """A new screen fades in from the background colour."""
        self.snap()
        self.forget()
        self._buttons = None  # the bar's buttons are not "new" on a new screen
        if not self.reduced:
            self._add("fade")

    def start(
        self,
        prev: State,
        new: State,
        result: object = None,
        direction: tuple[int, int] | None = None,
        undo: bool = False,
    ) -> None:
        """Build the timelines for one step from the two states. Any running
        timeline ends first, so a new input always starts from the right tile.
        `direction` is the move that was asked for; a move that went nowhere nudges.
        An `undo` runs from the state undone to the one restored, at double speed."""
        self.snap()
        self._pace = UNDO_PACE if undo else 1
        self._build(prev, new, result, direction, undo)
        self._pace = 1

    def _build(
        self,
        prev: State,
        new: State,
        result: object,
        direction: tuple[int, int] | None,
        undo: bool,
    ) -> None:
        if undo or prev.chamber is not new.chamber:
            self.forget()
        if self.reduced or prev.chamber is not new.chamber:
            return
        if isinstance(result, Failed):
            self._add("shake")
            self._add("vignette")
            return
        stepped = undo or (
            new.turns >= prev.turns and new.echo_index >= prev.echo_index
        )
        if stepped and _near(prev.player, new.player):
            self._add("slide", "player", prev.player, new.player)
        elif direction is not None and new.player == prev.player:
            self._add("nudge", "player", direction)
        if not undo and len(new.recording) > len(prev.recording):
            self._add("pop", len(new.recording) - 1)
        self._echo(prev, new, stepped, undo)
        for device_id in prev.gates_open ^ new.gates_open:
            self._add("gate", device_id, device_id in new.gates_open)
        for device_id in new.elevators_running - prev.elevators_running:
            self._add("elevator", device_id)
        timed = {pad.id: bool(pad.timer_length) for pad in new.chamber.pads}
        for pad_id in prev.pad_active ^ new.pad_active:
            self._add(
                "glow" if timed[pad_id] else "pad", pad_id, pad_id in new.pad_active
            )
        before = dict(prev.pad_timers)
        for pad_id, left in new.pad_timers:
            if timed[pad_id] and before.get(pad_id) != left:
                self._add("tick", pad_id)
        was, now = lighting.lit_tiles(prev), lighting.lit_tiles(new)
        if was != now:
            self._add("light", None, frozenset(now - was), frozenset(was - now))
        loads = _load(prev), _load(new)
        if loads[0] != loads[1]:
            self._add("power", None, *loads)
        if not undo:
            for energy in new.chamber.cells:
                if energy.id in new.cells_taken - prev.cells_taken:
                    self._add("sparkle", energy.id, energy.position)
        capacities = power.capacity_of(prev), power.capacity_of(new)
        if capacities[0] != capacities[1]:
            self._add("capacity", None, *capacities)
        if not undo and new.phase is Phase.RESULT and prev.phase is not Phase.RESULT:
            self._add("burst", None, new.player)

    def _echo(self, prev: State, new: State, stepped: bool, undo: bool) -> None:
        before, after = prev.echo_position, new.echo_position
        launched = not undo and (
            new.phase is Phase.REPLAY
            and (prev.phase is not Phase.REPLAY or new.echo_index < prev.echo_index)
        )
        if launched:
            self.forget()
        if undo:
            if before is not None and after is not None and _near(before, after):
                self._add("slide", "echo", before, after)
        elif launched and after is not None:
            self._add("spawn", "echo")
        elif (
            prev.phase is Phase.REPLAY
            and new.phase is Phase.REPLAY
            and before is not None
            and after is None
        ):
            self._add("expire", "echo", before)
        elif (
            stepped
            and before is not None
            and after is not None
            and _near(before, after)
        ):
            self._add("slide", "echo", before, after)
            self._trail = [*self._trail, before][-TRAIL_LENGTH:]

    def player(self, rest: Position) -> tuple[float, float, str | None]:
        """Where to draw the player in tiles, and a sprite id (None: the idle one)."""
        if (slid := self._get("slide", "player")) is not None:
            a, b = slid[1]
            x, y = slide(a, b, slid[0])
            return x, y, walk_sprite("player", slid[0])
        if (leaned := self._get("nudge", "player")) is not None:
            dx, dy = nudge(leaned[1][0], leaned[0])
            return rest.x + dx, rest.y + dy, None
        return float(rest.x), float(rest.y), None

    def echo(self, rest: Position | None) -> tuple[float, float, str | None] | None:
        """Where and how to draw the echo, or None when it is not on screen."""
        if (spawned := self._get("spawn", "echo")) is not None and rest is not None:
            return float(rest.x), float(rest.y), spawn_sprite(spawned[0])
        if (gone := self._get("expire", "echo")) is not None:
            at = gone[1][0]
            return float(at.x), float(at.y), expire_sprite(gone[0])
        if rest is None:
            return None
        if (slid := self._get("slide", "echo")) is not None:
            a, b = slid[1]
            x, y = slide(a, b, slid[0])
            return x, y, walk_sprite("echo", slid[0])
        return float(rest.x), float(rest.y), None

    def gate(self, device_id: str) -> str | None:
        found = self._get("gate", device_id)
        return None if found is None else gate_sprite(found[1][0], found[0])

    def elevator(self, device_id: str) -> str | None:
        found = self._get("elevator", device_id)
        return None if found is None else elevator_sprite(found[0])

    def pad(self, pad_id: str) -> str | None:
        if (found := self._get("pad", pad_id)) is not None:
            return pad_sprite(found[1][0], False, found[0])
        if (found := self._get("glow", pad_id)) is not None:
            return pad_sprite(found[1][0], True, found[0])
        return None

    def tick_lift(self, pad_id: str) -> float:
        found = self._get("tick", pad_id)
        return 0.0 if found is None else tick_lift(found[0])

    def light(self, pos: Position) -> tuple[bool, float] | None:
        """(was it lit, progress towards how it is now) for a tile fading, else None."""
        found = self._get("light")
        if found is None:
            return None
        gained, lost = found[1]
        if pos not in gained and pos not in lost:
            return None
        return pos in lost, light_progress(found[0])

    def shake(self) -> tuple[float, float]:
        found = self._get("shake")
        return (0.0, 0.0) if found is None else shake(found[0])

    def vignette(self) -> float:
        found = self._get("vignette")
        return 0.0 if found is None else vignette(found[0])

    def burst(self) -> tuple[Position, tuple[Particle, ...]] | None:
        found = self._get("burst")
        return None if found is None else (found[1][0], burst(found[0]))

    def fade(self) -> float:
        found = self._get("fade")
        return 0.0 if found is None else fade_alpha(found[0])

    def pop(self, index: int) -> float:
        """Size factor of timeline slot `index`: above 1 just after it is filled."""
        found = self._get("pop", index)
        return 1.0 if found is None else pop_scale(found[0])

    def power_load(self, load: int) -> float:
        """The load the power bar shows: easing to `load` after a change."""
        found = self._get("power")
        if found is None:
            return float(load)
        return eased_load(*found[1], found[0])

    def sparkles(self) -> list[tuple[Position, tuple[Particle, ...]]]:
        """Each energy cell just picked up with its sparks, for tile coordinates."""
        found = []
        for kind, key in self._effects:
            if kind == "sparkle" and (live := self._get(kind, key)) is not None:
                found.append((live[1][0], sparkle(live[0])))
        return found

    def capacity(self, capacity: int) -> float:
        """The capacity the power bar shows: easing to `capacity` after a change."""
        found = self._get("capacity")
        if found is None:
            return float(capacity)
        return eased_load(*found[1], found[0])

    def capacity_pulse(self) -> float:
        """0..1 swelling of the capacity bar frame while it grows, else 0."""
        found = self._get("capacity")
        if found is None or found[1][1] <= found[1][0]:
            return 0.0
        return capacity_pulse(found[0])

    def breath(self, offset: int = 0) -> float:
        """Tiles a resting figure is lifted by its breathing; none when reduced."""
        return 0.0 if self.reduced else breath(self.clock, offset)

    def pulse(self) -> float:
        """0..1 swelling of the playback slot; none when reduced."""
        return 0.0 if self.reduced else pulse(self.clock)

    def console_lit(self) -> bool:
        return not self.reduced and console_lit(self.clock)

    def conduit(self) -> float | None:
        """Where a pulse is along the conduit rails (0..1), or None when reduced."""
        return None if self.reduced else conduit(self.clock)

    def dust(self) -> tuple[Mote, ...]:
        return () if self.reduced else dust(self.clock)

    def trail(self, rest: Position | None) -> tuple[Position, ...]:
        """Where the echo just was, newest first, never its own tile."""
        if self.reduced or rest is None:
            return ()
        seen: list[Position] = []
        for at in reversed(self._trail):
            if at != rest and at not in seen:
                seen.append(at)
        return tuple(seen)

    def set_drawer(self, opened: bool, animate: bool = True) -> None:
        """Note whether the console drawer is open; a change starts it sliding."""
        if opened == self._drawer_open:
            return
        self._drawer_open = opened
        if animate and not self.reduced:
            self._add("drawer", None, opened)

    def drawer_hidden(self) -> float | None:
        """Share of the drawer still off screen while it slides, else None."""
        found = self._get("drawer")
        return None if found is None else drawer_hidden(found[1][0], found[0])

    def sync_buttons(self, shown: dict[str, object]) -> None:
        """Note the bottom-bar buttons on show; new and vanished ones slide."""
        before, self._buttons = self._buttons, shown
        if before is None or self.reduced:
            return
        for key in shown.keys() - before.keys():
            self._add("button", key, True, shown[key])
        for key in before.keys() - shown.keys():
            self._add("button", key, False, before[key])

    def button_hidden(self, key: str) -> float | None:
        """Share of a button still below the bar while it slides in, else None."""
        found = self._get("button", key)
        if found is None or not found[1][0]:
            return None
        return button_hidden(True, found[0])

    def leaving_buttons(self) -> list[tuple[object, float]]:
        """Buttons that just left the bar and how far they have sunk (0..1)."""
        gone = []
        for kind, key in self._effects:
            if kind != "button":
                continue
            found = self._get(kind, key)
            if found is not None and not found[1][0]:
                gone.append((found[1][1], button_hidden(False, found[0])))
        return gone
