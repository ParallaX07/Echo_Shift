"""Exhaustive search over the real turn engine.

Every transition here is `recording.act`, `recording.enter`, `recording.launch`
or `turn.step`; states are identified with `State.search_key()`. A search that
reaches its state or time cap reports `Verdict.INCONCLUSIVE` and never a verdict.

Cost model: only turn-consuming actions cost anything. A move or wait while
recording or replaying, and a console change made in either phase, costs one
turn. Free hub walking, free console changes before launch, starting a take,
saving it and launching cost nothing.
"""

import heapq
import itertools
import time
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from enum import Enum
from itertools import combinations

from . import lighting
from .model import Chamber, Phase, Position, State, TileType, initial_state
from .power import apply
from .recording import act, enter, launch
from .turn import Accepted, Failed, InteractAtConsole, Move, Rejected, Wait, step

DEFAULT_MAX_STATES = 200_000
DEFAULT_SOLUTION_CAP = 1_000
MOVES = {
    "up": Move(0, -1),
    "right": Move(1, 0),
    "down": Move(0, 1),
    "left": Move(-1, 0),
}
Token = str | dict
Trace = tuple[Token, ...]


class Verdict(str, Enum):
    SOLVABLE = "solvable"
    UNSOLVABLE = "unsolvable"
    INCONCLUSIVE = "inconclusive"


class Inconclusive(Exception):
    """A search hit its state or time cap before it could decide."""


@dataclass(frozen=True)
class Limits:
    """Caps for one search. `deadline` is a `time.monotonic()` value."""

    max_states: int = DEFAULT_MAX_STATES
    deadline: float | None = None

    @classmethod
    def seconds(cls, max_states: int, max_seconds: float | None) -> "Limits":
        deadline = None if max_seconds is None else time.monotonic() + max_seconds
        return cls(max_states, deadline)

    def check(self, visited: int) -> None:
        if visited > self.max_states:
            raise Inconclusive(f"more than {self.max_states} states")
        if self.deadline is not None and time.monotonic() > self.deadline:
            raise Inconclusive("time cap reached")


DEFAULT_LIMITS = Limits()


def power_choices(chamber: Chamber) -> tuple[frozenset[str], ...]:
    """Every power configuration the budget allows, smallest first."""
    ids = [circuit.id for circuit in chamber.circuits]
    return tuple(
        choice
        for size in range(len(ids) + 1)
        for names in combinations(ids, size)
        if apply(chamber, choice := frozenset(names)).ok
    )


def load_of(chamber: Chamber, config: frozenset[str]) -> int:
    return sum(c.load for c in chamber.circuits if c.id in config)


# --- No-echo exhaustion -----------------------------------------------------


@dataclass(frozen=True)
class Exhaustion:
    verdict: Verdict
    states: int


def exhaust_without_echo(
    chamber: Chamber,
    max_states: int = DEFAULT_MAX_STATES,
    max_seconds: float | None = None,
) -> Exhaustion:
    """Explore every play with no echo: free to walk, wait and use the console.

    `UNSOLVABLE` means the search ran to exhaustion without reaching the exit,
    `SOLVABLE` means it found the exit, and `INCONCLUSIVE` means a cap was hit.
    """
    return _exhaust(chamber, Limits.seconds(max_states, max_seconds))


def _exhaust(
    chamber: Chamber, limits: Limits, horizon: int | None = None
) -> Exhaustion:
    choices = power_choices(chamber)
    queue = deque(
        replace(initial_state(chamber, choice), phase=Phase.REPLAY)
        for choice in choices
    )
    seen = {state.search_key() for state in queue}
    actions = (
        *MOVES.values(),
        Wait(),
        *(InteractAtConsole(choice) for choice in choices),
    )
    try:
        while queue:
            state = queue.popleft()
            if horizon is not None and state.turns >= horizon:
                continue
            for action in actions:
                result = step(state, action)
                if not isinstance(result, Accepted):
                    continue
                if result.succeeded:
                    return Exhaustion(Verdict.SOLVABLE, len(seen))
                key = result.state.search_key()
                if key not in seen:
                    seen.add(key)
                    queue.append(result.state)
                    limits.check(len(seen))
    except Inconclusive:
        return Exhaustion(Verdict.INCONCLUSIVE, len(seen))
    return Exhaustion(Verdict.UNSOLVABLE, len(seen))


# --- Echo-allowed search ----------------------------------------------------


@dataclass(frozen=True)
class Constraints:
    """Restrictions on a search; the default allows every legal play."""

    max_load: int | None = None
    max_recorded: int | None = None
    launch: bool = True
    max_turns: int | None = None  # search horizon: ignore plays longer than this
    config_ok: Callable[[frozenset[str]], bool] | None = None
    state_ok: Callable[[State], bool] | None = None


UNCONSTRAINED = Constraints()


@dataclass(frozen=True)
class Outcome:
    verdict: Verdict
    turns: int | None = None
    trace: Trace = ()
    solutions: int = 0  # distinct shortest solutions (counting runs only)
    capped: bool = False  # `solutions` is a lower bound
    states: int = 0


GOAL = "goal"


def _key(state: State) -> tuple[object, ...]:
    """`search_key()` of the state, ignoring the recording once the echo is gone.

    A replay with no echo never reads the recording again (failed attempts are
    not explored), so plays that differ only in a spent recording share a key.
    """
    if state.phase is Phase.REPLAY and state.echo_position is None:
        state = replace(
            state, recording=(), echo_index=0, echo_hold=0, retry_snapshot=None
        )
    return state.search_key()


class _Search:
    def __init__(
        self, chamber: Chamber, cons: Constraints, limits: Limits, count_cap: int
    ):
        self.chamber = chamber
        self.cons = cons
        self.limits = limits
        self.count_cap = count_cap
        self.choices = tuple(
            c
            for c in power_choices(chamber)
            if (cons.max_load is None or load_of(chamber, c) <= cons.max_load)
            and (cons.config_ok is None or cons.config_ok(c))
        )
        self.paths = self._hub_paths()
        self.consoles = sorted(chamber.consoles)

    def _hub_paths(self) -> dict[tuple[Position, Position], tuple[str, ...]]:
        hub = self.chamber.hub
        paths = {}
        for origin in hub:
            paths[origin, origin] = ()
            queue = deque([origin])
            while queue:
                here = queue.popleft()
                for token, move in MOVES.items():
                    there = Position(here.x + move.dx, here.y + move.dy)
                    if there in hub and (origin, there) not in paths:
                        paths[origin, there] = (*paths[origin, here], token)
                        queue.append(there)
        return paths

    def _walk(self, state: State, tokens: tuple[str, ...]) -> State | None:
        for token in tokens:
            result = act(state, MOVES[token])
            if not isinstance(result, Accepted):
                return None
            state = result.state
        return state

    def _to_console(self, state: State) -> tuple[State, tuple[Token, ...]] | None:
        """Walk to the nearest console; None when no console is reachable."""
        options = [
            (len(self.paths[state.player, tile]), tile)
            for tile in self.consoles
            if (state.player, tile) in self.paths
        ]
        if not options:
            return None
        tokens = self.paths[state.player, min(options)[1]]
        walked = self._walk(state, tokens)
        return None if walked is None else (walked, tokens)

    def _configured(
        self, state: State, config: frozenset[str]
    ) -> tuple[State, tuple[Token, ...]] | None:
        """Free power change at the hub console, with the walk to reach it."""
        if config == state.powered_circuits:
            return state, ()
        reached = self._to_console(state)
        if reached is None:
            return None
        walked, tokens = reached
        result = act(walked, InteractAtConsole(config))
        if not isinstance(result, Accepted):
            return None
        return result.state, (*tokens, {"power": sorted(config)})

    def edges(self, state: State) -> Iterator[tuple]:
        """Yield (child, cost, tokens, label, exited) for each legal next step."""
        if state.phase is Phase.PREPARE:
            yield from self._roots(state)
        elif state.phase is Phase.RECORDING:
            yield from self._turns(state, recording=True)
            yield enter(state), 0, ("enter",), ("save",), False
        elif state.phase is Phase.COMMITTED:
            if self.cons.launch:
                yield from self._launches(state)
        elif state.phase is Phase.REPLAY:
            yield from self._turns(state, recording=False)

    def _roots(self, state: State) -> Iterator[tuple]:
        for config in self.choices:
            configured = self._configured(state, config)
            if configured is None:
                continue
            ready, tokens = configured
            for tile in sorted(self.chamber.hub):
                path = self.paths.get((ready.player, tile))
                walked = None if path is None else self._walk(ready, path)
                if walked is None:
                    continue
                started = enter(walked)
                if started is walked:
                    continue
                yield started, 0, (*tokens, *path, "enter"), ("enter", tile), False

    def _launches(self, state: State) -> Iterator[tuple]:
        for config in self.choices:
            configured = self._configured(state, config)
            if configured is None:
                continue
            ready, tokens = configured
            launched = launch(ready)
            if launched is ready:
                continue
            if self.cons.state_ok is not None and not self.cons.state_ok(launched):
                continue
            label = ("launch", tuple(sorted(config)))
            yield launched, 0, (*tokens, "launch"), label, False

    def _walled(self, here: Position, move: Move) -> bool:
        """Cheap skip of moves the engine would reject for a wall anyway."""
        tile = self.chamber.tile_at(Position(here.x + move.dx, here.y + move.dy))
        return tile is TileType.WALL

    def _turns(self, state: State, recording: bool) -> Iterator[tuple]:
        limit = self.cons.max_recorded
        can_record = not (
            recording and limit is not None and len(state.recording) >= limit
        )
        steps = []
        if can_record:
            steps += [
                (move, token, token)
                for token, move in MOVES.items()
                if not self._walled(state.player, move)
            ]
            steps.append((Wait(), "wait", "wait"))
        if state.player in self.chamber.consoles:
            for config in self.choices:
                if config != state.powered_circuits:
                    label = ("power", tuple(sorted(config)))
                    steps.append(
                        (InteractAtConsole(config), {"power": sorted(config)}, label)
                    )
        for action, token, label in steps:
            result = act(state, action)
            if isinstance(result, (Rejected, Failed)):
                continue
            child = result.state
            if not recording and self.cons.state_ok and not self.cons.state_ok(child):
                continue
            yield child, 1, (token,), label, result.succeeded

    def run(self, count: bool) -> Outcome:
        """Dijkstra over zero-or-one-cost edges; `count` also counts shortest plays."""
        start = initial_state(self.chamber)
        root = _key(start)
        dist: dict[object, int] = {root: 0}
        parents: dict[object, list[tuple[object, tuple, object]]] = {root: []}
        tie = itertools.count()
        heap = [(0, next(tie), start)]
        best = None
        while heap:
            cost, _, state = heapq.heappop(heap)
            if best is not None and cost > best:
                break
            key = _key(state)
            if cost > dist[key]:
                continue
            for child, step_cost, tokens, label, exited in self.edges(state):
                total = cost + step_cost
                if self.cons.max_turns is not None and total > self.cons.max_turns:
                    continue
                target = GOAL if exited else _key(child)
                known = dist.get(target)
                if known is None or total < known:
                    dist[target] = total
                    parents[target] = [(key, tokens, label)]
                elif total == known and count:
                    parents[target].append((key, tokens, label))
                    continue
                else:
                    continue
                if exited:
                    best = total if best is None else min(best, total)
                    if not count:
                        return Outcome(
                            Verdict.SOLVABLE,
                            total,
                            self._trace(parents, GOAL),
                            states=len(dist),
                        )
                else:
                    heapq.heappush(heap, (total, next(tie), child))
                self.limits.check(len(dist))
        if best is None:
            return Outcome(Verdict.UNSOLVABLE, states=len(dist))
        trace = self._trace(parents, GOAL)
        solutions, capped = self._count(parents)
        return Outcome(Verdict.SOLVABLE, best, trace, solutions, capped, len(dist))

    @staticmethod
    def _trace(parents: dict, goal: object) -> Trace:
        chunks = []
        key = goal
        while parents[key]:
            key, tokens, _ = parents[key][0]
            chunks.append(tokens)
        return tuple(token for chunk in reversed(chunks) for token in chunk)

    def _count(self, parents: dict) -> tuple[int, bool]:
        """Count distinct label sequences over every shortest path to the exit."""
        cap = self.count_cap
        memo: dict[object, frozenset] = {}
        capped = False

        def sequences(key: object) -> frozenset:
            nonlocal capped
            if key in memo:
                return memo[key]
            if not parents[key]:
                memo[key] = frozenset({()})
                return memo[key]
            found: set = set()
            for parent, _, label in parents[key]:
                for before in sequences(parent):
                    found.add((*before, label))
                    if len(found) > cap:
                        capped = True
                        break
                if len(found) > cap:
                    break
            memo[key] = frozenset(found)
            return memo[key]

        return min(len(sequences(GOAL)), cap), capped


def explore(
    chamber: Chamber,
    cons: Constraints = UNCONSTRAINED,
    limits: Limits = DEFAULT_LIMITS,
    *,
    count: bool = False,
    count_cap: int = DEFAULT_SOLUTION_CAP,
) -> Outcome:
    """Find the fewest turns to the exit, with a replayable trace.

    `count=True` also counts distinct shortest solutions (see `docs/rules.md`).
    """
    try:
        return _Search(chamber, cons, limits, count_cap).run(count)
    except Inconclusive:
        return Outcome(Verdict.INCONCLUSIVE)


def play(chamber: Chamber, trace: Trace) -> tuple[bool, int, int, int]:
    """Replay a trace on the real engine: (exited, turns, recorded, peak load)."""
    state = initial_state(chamber)
    peak = 0
    exited = False
    for token in trace:
        if isinstance(token, dict):
            action = InteractAtConsole(frozenset(token["power"]))
        elif token == "enter":
            state = enter(state)
            continue
        elif token == "launch":
            state = launch(state)
            continue
        elif token == "wait":
            action = Wait()
        else:
            action = MOVES[token]
        before = state
        result = act(state, action)
        state = result.state
        if isinstance(result, Accepted) and (
            before.phase in (Phase.RECORDING, Phase.REPLAY)
        ):
            peak = max(peak, load_of(chamber, state.powered_circuits))
        exited = isinstance(result, Accepted) and result.succeeded
        if exited:
            break
    return exited, state.turns, len(state.recording), peak


# --- Taught ideas -----------------------------------------------------------


def _full(chamber: Chamber) -> Callable[[frozenset[str]], bool]:
    everything = frozenset(c.id for c in chamber.circuits)
    return lambda config: config == everything


def _echo_on_lit_tile(state: State) -> bool:
    return state.echo_position is None or state.echo_position in lighting.lit_tiles(
        state
    )


def _solvable(chamber: Chamber, cons: Constraints, limits: Limits) -> bool:
    outcome = explore(chamber, cons, limits)
    if outcome.verdict is Verdict.INCONCLUSIVE:
        raise Inconclusive("idea check hit a cap")
    return outcome.verdict is Verdict.SOLVABLE


def features(chamber: Chamber) -> tuple[str, ...]:
    """The ideas a chamber actually exercises, for `combined` chambers."""
    found = ["echo"]
    if sum(c.load for c in chamber.circuits) > chamber.capacity:
        found.append("power")
    if any(circuit.zones for circuit in chamber.circuits):
        found.append("darkness")
    if any(pad.timer_length > 0 for pad in chamber.pads):
        found.append("timed_pads")
    return tuple(found)


def avoids_idea(
    chamber: Chamber,
    idea: str,
    limits: Limits = DEFAULT_LIMITS,
    horizon: int | None = None,
) -> bool:
    """True when some solution gets by without the taught idea.

    - movement: solvable with no circuit ever powered (no lit route needed).
    - power: solvable with every circuit powered all the time (no allocation).
    - echo: solvable with an empty recording, or with no echo at all.
    - darkness: solvable with the echo never standing on an unlit tile.
    - timed_pads: still solvable when every pad timer is zero.
    - combined: avoids any one idea the chamber exercises.

    Every check covers all plays, or only those of at most `horizon` turns.
    Raises `Inconclusive` when a cap is hit.
    """
    if idea == "movement":
        return _solvable(
            chamber, Constraints(max_turns=horizon, config_ok=lambda c: not c), limits
        )
    if idea == "power":
        return _solvable(
            chamber, Constraints(max_turns=horizon, config_ok=_full(chamber)), limits
        )
    if idea == "echo":
        if _solvable(chamber, Constraints(max_recorded=0, max_turns=horizon), limits):
            return True
        outcome = _exhaust(chamber, limits, horizon)
        if outcome.verdict is Verdict.INCONCLUSIVE:
            raise Inconclusive("no-echo exhaustion hit a cap")
        return outcome.verdict is Verdict.SOLVABLE
    if idea == "darkness":
        return _solvable(
            chamber, Constraints(max_turns=horizon, state_ok=_echo_on_lit_tile), limits
        )
    if idea == "timed_pads":
        flat = replace(
            chamber, pads=tuple(replace(pad, timer_length=0) for pad in chamber.pads)
        )
        return _solvable(flat, Constraints(max_turns=horizon), limits)
    if idea == "combined":
        return any(
            avoids_idea(chamber, part, limits, horizon) for part in features(chamber)
        )
    raise ValueError(f"unknown idea: {idea}")


# --- Report -----------------------------------------------------------------


@dataclass(frozen=True)
class Report:
    verdict: Verdict
    reason: str = ""
    turns: int | None = None  # fewest total turns
    trace: Trace = ()  # a replayable play with that many turns (fewest recorded)
    recorded: int | None = None  # fewest recorded commands
    recorded_turns: int | None = None  # fewest turns among those plays
    recorded_trace: Trace = ()
    peak_load: int | None = None  # lowest peak power load
    solutions: int = 0  # distinct shortest solutions
    solutions_capped: bool = False
    idea: str | None = None
    avoids_idea: bool | None = None


def analyze(
    chamber: Chamber,
    max_states: int = DEFAULT_MAX_STATES,
    max_seconds: float | None = None,
    solution_cap: int = DEFAULT_SOLUTION_CAP,
    idea_horizon: int | None = None,
) -> Report:
    """Solve a chamber from its start; any capped sub-search makes it inconclusive.

    `idea_horizon` limits the idea check to plays of at most that many turns;
    the default checks every play.
    """
    limits = Limits.seconds(max_states, max_seconds)
    try:
        main = explore(chamber, limits=limits, count=True, count_cap=solution_cap)
        if main.verdict is Verdict.INCONCLUSIVE:
            raise Inconclusive("shortest-solution search hit a cap")
        if main.verdict is Verdict.UNSOLVABLE:
            return Report(Verdict.UNSOLVABLE, idea=chamber.idea)
        recorded, fewest = _fewest_recorded(chamber, limits)
        trace = (
            fewest.trace
            if fewest.turns == main.turns
            else _shortest_with_fewest_recorded(chamber, main, recorded, limits)
        )
        peak = _lowest_peak(chamber, main.turns, limits)
        avoided = (
            avoids_idea(chamber, chamber.idea, limits, idea_horizon)
            if chamber.idea
            else None
        )
    except Inconclusive as exc:
        return Report(Verdict.INCONCLUSIVE, str(exc), idea=chamber.idea)
    return Report(
        Verdict.SOLVABLE,
        turns=main.turns,
        trace=trace,
        recorded=recorded,
        recorded_turns=fewest.turns,
        recorded_trace=fewest.trace,
        peak_load=peak,
        solutions=main.solutions,
        solutions_capped=main.capped,
        idea=chamber.idea,
        avoids_idea=avoided,
    )


def _checked(outcome: Outcome) -> Outcome:
    if outcome.verdict is Verdict.INCONCLUSIVE:
        raise Inconclusive("search hit a cap")
    return outcome


def _fewest_recorded(chamber: Chamber, limits: Limits) -> tuple[int, Outcome]:
    for recorded in range(chamber.max_turns + 1):
        outcome = _checked(explore(chamber, Constraints(max_recorded=recorded), limits))
        if outcome.verdict is Verdict.SOLVABLE:
            return recorded, outcome
    raise Inconclusive("no solution within the recording limit")


def _shortest_with_fewest_recorded(
    chamber: Chamber, main: Outcome, floor: int, limits: Limits
) -> Trace:
    for recorded in range(floor, chamber.max_turns + 1):
        outcome = _checked(explore(chamber, Constraints(max_recorded=recorded), limits))
        if outcome.turns == main.turns:
            return outcome.trace
    return main.trace


def _lowest_peak(chamber: Chamber, turns: int, limits: Limits) -> int:
    """Lowest peak load among the plays that take the fewest turns."""
    for peak in sorted({load_of(chamber, c) for c in power_choices(chamber)}):
        cons = Constraints(max_load=peak, max_turns=turns)
        outcome = _checked(explore(chamber, cons, limits))
        if outcome.verdict is Verdict.SOLVABLE:
            return peak
    raise Inconclusive("no solution under any power load")
