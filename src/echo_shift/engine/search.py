"""Exhaustive search over the real turn engine.

Every transition here is `recording.act`, `recording.enter`, `recording.launch`
or `turn.step`; states are identified with `State.search_key()`
(with equivalent echoes merged, see `_Keys`). A search that
reaches its state or time cap reports `Verdict.INCONCLUSIVE` and never a verdict.

Cost model: only turn-consuming actions cost anything. A move or wait while
recording or replaying, and a console change made in either phase, costs one
turn. Free roam over lit tiles before a take and between a take and its launch
(which also picks up energy cells and changes power at a console), starting a
take, saving it and launching cost nothing.
"""

import heapq
import itertools
import time
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from enum import Enum
from functools import lru_cache
from itertools import combinations

from . import lighting
from .model import Chamber, Phase, Position, State, TileType, initial_state
from .power import apply, max_capacity
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


def power_choices(
    chamber: Chamber, capacity: int | None = None
) -> tuple[frozenset[str], ...]:
    """Every power configuration `capacity` allows (base if omitted), smallest first."""
    ids = [circuit.id for circuit in chamber.circuits]
    return tuple(
        choice
        for size in range(len(ids) + 1)
        for names in combinations(ids, size)
        if apply(chamber, choice := frozenset(names), capacity).ok
    )


def load_of(chamber: Chamber, config: frozenset[str]) -> int:
    return sum(c.load for c in chamber.circuits if c.id in config)


# --- Free roam ----------------------------------------------------------------

Node = tuple[Position, frozenset[str], frozenset[str]]  # tile, powered, cells taken


def _node(state: State) -> Node:
    return state.player, state.powered_circuits, state.cells_taken


class RoamGraph:
    """Everything free roam can do before a take and before a launch, at no cost.

    In `PREPARE` and `COMMITTED` the player walks onto lit tiles, changes power at
    a console and picks up cells for no turns, and the world never reacts. What
    the player can reach is therefore a graph on `(tile, powered circuits, cells
    taken)` whose edges are `recording.act` calls, and whatever a search wants from
    free roam (where to start a take, what to launch with) is read off the part of
    that graph reachable from where the player stands. Taking the closure instead
    of choosing a walk is exact: moving costs nothing, so no walk beats another.

    The graph is the same for every take and every launch. Free roam never touches
    the recording, the echo, the pad timers or the turn count, and the devices it
    leaves behind (no gate or lift is ever open, since no pad is active with the
    player in the hub and the timers at zero) depend only on the node. One graph
    per chamber is therefore built lazily and shared, and a search that wants
    fewer power settings (a constraint) filters the console edges instead of
    building its own.

    Cells are taken here and nowhere else: a turn never picks one up, so the cells
    taken are fixed from the end of free roam through the take and the replay.
    More cells never hurt: capacity only grows, so a console edge that was open
    stays open. The closure itself does not prune on that; every reachable
    `(powered, cells)` is kept, because the state key tells them apart.
    """

    def __init__(self, chamber: Chamber):
        self.chamber = chamber
        # Every setting some capacity allows; `act` checks the one in force.
        self.configs = power_choices(chamber, max_capacity(chamber))
        self._states: dict[Node, State] = {}
        self._edges: dict[Node, tuple[tuple[Token, Node, frozenset | None], ...]] = {}
        self._reach: dict[tuple[Node, frozenset], dict[Node, tuple[Token, ...]]] = {}

    def root(self, powered: frozenset[str], cells: frozenset[str]) -> Node:
        """The node of a player standing on the start tile with this much done."""
        node = (self.chamber.start, powered, cells)
        if node not in self._states:
            self._states[node] = initial_state(self.chamber, powered, cells)
        return node

    def state(self, node: Node) -> State:
        """The `PREPARE` state a player in free roam reaches at this node."""
        return self._states[node]

    def edges(self, node: Node) -> tuple[tuple[Token, Node, frozenset | None], ...]:
        """(token, child, power setting or None) for each legal free action."""
        found = self._edges.get(node)
        if found is None:
            state = self._states[node]
            out = []
            for token, move in MOVES.items():
                result = act(state, move)
                if isinstance(result, Accepted):
                    child = _node(result.state)
                    self._states.setdefault(child, result.state)
                    out.append((token, child, None))
            if state.player in self.chamber.consoles:
                for config in self.configs:
                    if config == state.powered_circuits:
                        continue
                    result = act(state, InteractAtConsole(config))
                    if isinstance(result, Accepted):
                        child = _node(result.state)
                        self._states.setdefault(child, result.state)
                        out.append(({"power": sorted(config)}, child, config))
            found = self._edges[node] = tuple(out)
        return found

    def reach(
        self, root: Node, allowed: frozenset, limits: Limits | None = None
    ) -> dict[Node, tuple[Token, ...]]:
        """Every node free roam reaches from `root`, with a shortest walk to it.

        Console edges to a setting outside `allowed` are not taken.
        """
        key = (root, allowed)
        found = self._reach.get(key)
        if found is None:
            found = {root: ()}
            queue = deque([root])
            while queue:
                here = queue.popleft()
                for token, there, config in self.edges(here):
                    if (config is None or config in allowed) and there not in found:
                        found[there] = (*found[here], token)
                        queue.append(there)
                        if limits is not None:
                            limits.check(len(found))
            self._reach[key] = found
        return found


@lru_cache(maxsize=16)
def roam_graph(chamber: Chamber) -> RoamGraph:
    return RoamGraph(chamber)


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
    """Plain search over every play in which the echo never acts.

    A play in two parts, as in the game. Part one is a take: the player starts it
    on any hub tile free roam reaches, then moves, waits and uses the console for
    up to `max_turns` recorded commands (console changes record nothing), with no
    echo in the world. Part two is the replay: after a free roam of the take's end
    (which may pick up cells and change power at the console) the chamber resets
    with the power and cells carried, and the player plays on with no echo, for as
    long as it likes. The exit counts in either part. Cells come only from free
    roam, so a turn never adds capacity, but every power change is valid at the
    capacity the cells taken so far give.

    An echo that did act could only be given more to work with, so a chamber that
    no such play solves needs an echo; the search is exhaustive, so it is a proof.
    """
    roam = roam_graph(chamber)
    everything = frozenset(roam.configs)
    actions = (*MOVES.values(), Wait(), *(InteractAtConsole(c) for c in roam.configs))
    tie = itertools.count()
    heap: list[tuple[int, int, State, int | None]] = []  # turns, tie, state, used
    seen: set[object] = set()
    launched: set[Node] = set()

    def push(state: State, used: int | None) -> None:
        # `used` counts recorded commands in a take and is None during the replay.
        key = (state.search_key(), used, state.turns if horizon is not None else 0)
        if key not in seen:
            seen.add(key)
            heapq.heappush(heap, (state.turns, next(tie), state, used))
            limits.check(len(seen))

    def commit(state: State) -> None:
        """Save the take as it stands and launch, after a free roam in between."""
        root = roam.root(state.powered_circuits, state.cells_taken)
        if root in launched:
            return
        launched.add(root)
        for tile, config, cells in roam.reach(root, everything, limits):
            if tile in chamber.hub:
                reset = initial_state(chamber, config, cells)
                push(replace(reset, turns=state.turns, phase=Phase.REPLAY), None)

    try:
        start = roam.root(frozenset(), frozenset())
        for node in roam.reach(start, everything, limits):
            if node[0] in chamber.hub:
                push(replace(roam.state(node), phase=Phase.RECORDING, turns=0), 0)
        while heap:
            turns, _, state, used = heapq.heappop(heap)
            if used is not None:
                commit(state)
                if used >= chamber.max_turns:
                    continue  # the recording is full
            if horizon is not None and turns >= horizon:
                continue
            for action in actions:
                result = step(state, action)
                if not isinstance(result, Accepted):
                    continue
                if result.succeeded:
                    return Exhaustion(Verdict.SOLVABLE, len(seen))
                if used is None:
                    push(result.state, None)
                else:
                    recorded = not isinstance(action, InteractAtConsole)
                    push(result.state, used + recorded)
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
    echo_safe: bool = False  # the echo never stands on an unlit tile or live conduit


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
UNREACHABLE = 10**6  # a distance no play reaches


NOWHERE = Position(-1, -1)  # stands for "an echo, wherever it is" in a state key


class _Keys:
    """State identity for the search: `State.search_key()` with equal echoes merged.

    The echo reaches the world through one thing, the pad it stands on each turn.
    While it follows its recording undisturbed, where it stands off a pad does not
    matter, so two takes that put the echo on the same pads on the same turns are
    interchangeable once saved: replayed from the same state they play out the same,
    for the echo and for everything it touches. A replay therefore needs only the
    pads the echo is still to stand on, and one with none left is a replay with no
    echo. While a take is being recorded the length and the pads so far are kept,
    because the commands appended next carry on from them.

    The echo is disturbed only when a command takes it onto a closed gate, and a
    gate tile has to be on the recording's own route for that, so a recording whose
    route never touches a gate tile is merged this way. One that does keeps its
    commands in the key, and so does every recording when an opaque constraint reads
    the state (`exact`). A constraint on the echo's safety (`granular`) also needs
    what lights each tile it crosses and which conduits run under it, so tiles are
    told apart by that too. A retry snapshot never matters: attempts that fail are
    not explored, so nothing returns to it. A search then pays for the routes that
    differ in what they do to the world, not for every walk through a hub or wing.
    """

    def __init__(self, chamber: Chamber, exact: bool, granular: bool):
        self.exact = exact
        self.chamber = chamber
        self.granular = granular
        self.gates = frozenset(
            device.position
            for device in chamber.devices
            if device.kind is TileType.GATE
        )
        self.pads = {pad.position: pad.id for pad in chamber.pads}
        self._routes: dict[tuple[Position, tuple], tuple | None] = {}
        self._labels: dict[Position, object] = {}

    def label(self, tile: Position) -> object:
        """What the world and the constraints can tell about a tile the echo is on."""
        found = self._labels.get(tile, False)
        if found is False:
            found = self.pads.get(tile)
            if self.granular:
                chamber = self.chamber
                zones = {z.id: z for z in chamber.zones if tile in z.tiles}
                lit = (
                    True
                    if tile in chamber.hub
                    else frozenset(
                        c.id for c in chamber.circuits if zones.keys() & set(c.zones)
                    )
                )
                live = frozenset(
                    c.circuit_id for c in chamber.conduits if tile in c.tiles
                )
                found = (found, lit, live)
            self._labels[tile] = found
        return found

    def route(self, start: Position, recording: tuple) -> tuple | None:
        """The label under the echo after each command, or None if it nears a gate."""
        known = self._routes.get((start, recording), False)
        if known is not False:
            return known
        at, labels = start, []
        for command in recording:
            if isinstance(command, Move):
                at = Position(at.x + command.dx, at.y + command.dy)
                if at in self.gates:
                    self._routes[start, recording] = None
                    return None
            labels.append(self.label(at))
        found = self._routes[start, recording] = (*labels, self.label(at))
        return found

    def __call__(self, state: State) -> tuple[object, ...]:
        replaying = state.phase is Phase.REPLAY
        if replaying and state.echo_position is None:
            ahead = ()  # with no echo the recording is never read again
        elif self.exact or state.echo_start is None:
            return replace(state, retry_snapshot=None).search_key()
        else:
            route = self.route(state.echo_start, state.recording)
            if route is None:
                return replace(state, retry_snapshot=None).search_key()
            # The echo holds its last tile for one more turn after the recording.
            ahead = route
            if replaying:
                ahead = ahead[state.echo_index + state.echo_hold :]
                while ahead and ahead[-1] is None:
                    ahead = ahead[:-1]
            elif state.phase is Phase.RECORDING:
                ahead = route[:-1]  # more commands are still to come
        gone = replaying and not ahead
        return replace(
            state,
            recording=() if gone else ("route", ahead),
            echo_start=NOWHERE,
            echo_index=0,
            echo_hold=0,
            echo_position=None if gone or state.echo_position is None else NOWHERE,
            retry_snapshot=None,
        ).search_key()


class _Search:
    def __init__(
        self, chamber: Chamber, cons: Constraints, limits: Limits, count_cap: int
    ):
        self.chamber = chamber
        self.cons = cons
        self.limits = limits
        self.count_cap = count_cap
        self.roam = roam_graph(chamber)
        self._key = _Keys(chamber, cons.state_ok is not None, cons.echo_safe)
        self.choices = tuple(
            c
            for c in self.roam.configs
            if (cons.max_load is None or load_of(chamber, c) <= cons.max_load)
            and (cons.config_ok is None or cons.config_ok(c))
        )
        self.allowed = frozenset(self.choices)

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

    def _free_roam(self, state: State) -> dict[Node, tuple[Token, ...]]:
        root = self.roam.root(state.powered_circuits, state.cells_taken)
        return self.roam.reach(root, self.allowed, self.limits)

    def _roots(self, state: State) -> Iterator[tuple]:
        """Start a take on any hub tile free roam reaches, with any power and cells.

        This is only asked of the first state of a search.
        """
        for node, path in self._free_roam(state).items():
            tile, config, _ = node
            if tile not in self.chamber.hub or config not in self.allowed:
                continue
            ready = self.roam.state(node)
            started = enter(ready)
            if started is not ready:
                yield started, 0, (*path, "enter"), ("enter",), False

    def _launches(self, state: State) -> Iterator[tuple]:
        """Launch after a free roam: any power and cells it reaches at a hub tile."""
        done = set()
        for node, path in self._free_roam(state).items():
            tile, config, cells = node
            if tile not in self.chamber.hub or config not in self.allowed:
                continue
            if (config, cells) in done:
                continue
            done.add((config, cells))
            ready = replace(
                state, player=tile, powered_circuits=config, cells_taken=cells
            )
            launched = launch(ready)
            if launched is ready:
                continue
            if not self._acceptable(launched):
                continue
            label = ("launch", tuple(sorted(config)))
            yield launched, 0, (*path, "launch"), label, False

    def _acceptable(self, state: State) -> bool:
        """Whether a replay state passes the constraints on the play."""
        cons = self.cons
        if cons.state_ok is not None and not cons.state_ok(state):
            return False
        return not (cons.echo_safe and not _echo_on_safe_tile(state))

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
            if not recording and not self._acceptable(child):
                continue
            yield child, 1, (token,), label, result.succeeded

    def _distances(self) -> dict[Position, int]:
        """Moves from each tile to the exit if gates, light and power never mattered."""
        chamber, exit_tile = self.chamber, self.chamber.exit
        found = {} if exit_tile is None else {exit_tile: 0}
        queue = deque(found)
        while queue:
            here = queue.popleft()
            for move in MOVES.values():
                there = Position(here.x + move.dx, here.y + move.dy)
                if there not in found and chamber.tile_at(there) is not TileType.WALL:
                    found[there] = found[here] + 1
                    queue.append(there)
        return found

    def _toward_exit(self, state: State) -> int:
        """A lower bound on the turns still to play, the same for equal keys.

        A replay needs at least as many turns as the player has tiles to cross.
        A take that is still being recorded may end by walking to the exit or by
        saving and replaying from the start, so it needs the lesser of the two;
        before a take, or while one is saved, only the replay's walk and the
        start of a take count (a take can start anywhere in the hub). The bound
        never falls along a free step and falls by at most one along a turn, so
        searching in order of turns so far plus this bound stays exact.
        """
        far = self.far
        if state.phase is Phase.REPLAY:
            return far.get(state.player, UNREACHABLE)
        replay = far.get(self.chamber.start, UNREACHABLE)
        if state.phase is Phase.RECORDING:
            return min(far.get(state.player, UNREACHABLE), replay)
        if state.phase is Phase.COMMITTED:
            return replay
        return min(far.get(tile, UNREACHABLE) for tile in self.chamber.hub)

    def run(self, count: bool) -> Outcome:
        """A* over zero-or-one-cost edges; `count` also counts shortest plays."""
        self.far = self._distances()
        start = initial_state(self.chamber)
        root = self._key(start)
        dist: dict[object, int] = {root: 0}
        parents: dict[object, list[tuple[object, tuple, object]]] = {root: []}
        tie = itertools.count()
        bound = self._toward_exit(start)
        heap = [(bound, bound, next(tie), 0, start)]
        best = None
        while heap:
            priority, _, _, cost, state = heapq.heappop(heap)
            if best is not None and priority >= best + count:
                break
            key = self._key(state)
            if cost > dist[key]:
                continue
            for child, step_cost, tokens, label, exited in self.edges(state):
                total = cost + step_cost
                ahead = 0 if exited else self._toward_exit(child)
                if self.cons.max_turns is not None and (
                    total + ahead > self.cons.max_turns
                ):
                    continue
                target = GOAL if exited else self._key(child)
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
                else:
                    entry = (total + ahead, ahead, next(tie), total, child)
                    heapq.heappush(heap, entry)
                self.limits.check(len(dist))
        if best is None:
            return Outcome(Verdict.UNSOLVABLE, states=len(dist))
        trace = self._trace(parents, GOAL)
        if not count:
            return Outcome(Verdict.SOLVABLE, best, trace, states=len(dist))
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


def _echo_on_safe_tile(state: State) -> bool:
    """The echo is not on an unlit tile or a live conduit (it is immune to both)."""
    return state.echo_position is None or lighting.is_safe(state, state.echo_position)


def _solvable(chamber: Chamber, cons: Constraints, limits: Limits) -> bool:
    outcome = explore(chamber, cons, limits)
    if outcome.verdict is Verdict.INCONCLUSIVE:
        raise Inconclusive("idea check hit a cap")
    return outcome.verdict is Verdict.SOLVABLE


def features(chamber: Chamber) -> tuple[str, ...]:
    """The ideas a chamber actually exercises, for `combined` chambers."""
    found = ["echo"]
    if chamber.cells or sum(c.load for c in chamber.circuits) > chamber.capacity:
        found.append("power")
    if chamber.conduits or any(circuit.zones for circuit in chamber.circuits):
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
      Cells count: a setting is valid at the capacity in force, so powering
      everything can wait for a cell, but only when the cell can be reached
      without powering less first.
    - echo: solvable with an empty recording, or with no echo at all.
    - darkness: solvable with the echo never on an unlit tile or a live conduit.
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
        cons = Constraints(max_recorded=0, max_turns=horizon)
        if _solvable(chamber, cons, limits):
            return True
        outcome = _exhaust(chamber, limits, horizon)
        if outcome.verdict is Verdict.INCONCLUSIVE:
            raise Inconclusive("no-echo exhaustion hit a cap")
        return outcome.verdict is Verdict.SOLVABLE
    if idea == "darkness":
        return _solvable(
            chamber, Constraints(max_turns=horizon, echo_safe=True), limits
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
        cons = Constraints(max_recorded=recorded)
        outcome = _checked(explore(chamber, cons, limits))
        if outcome.verdict is Verdict.SOLVABLE:
            return recorded, outcome
    raise Inconclusive("no solution within the recording limit")


def _shortest_with_fewest_recorded(
    chamber: Chamber, main: Outcome, floor: int, limits: Limits
) -> Trace:
    for recorded in range(floor, chamber.max_turns + 1):
        cons = Constraints(max_recorded=recorded)
        outcome = _checked(explore(chamber, cons, limits))
        if outcome.turns == main.turns:
            return outcome.trace
    return main.trace


def _lowest_peak(chamber: Chamber, turns: int, limits: Limits) -> int:
    """Lowest peak load among the plays that take the fewest turns."""
    loads = {load_of(chamber, c) for c in roam_graph(chamber).configs}
    for peak in sorted(loads):
        cons = Constraints(max_load=peak, max_turns=turns)
        outcome = _checked(explore(chamber, cons, limits))
        if outcome.verdict is Verdict.SOLVABLE:
            return peak
    raise Inconclusive("no solution under any power load")
