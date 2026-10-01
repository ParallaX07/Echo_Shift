"""Validated lesson data and progress, independent of rendering and input."""

from dataclasses import dataclass

from echo_shift.engine.loader import LevelError
from echo_shift.engine.model import Chamber, State

ACTIONS = {
    "open_console",
    "toggle",
    "apply",
    "enter",
    "launch",
    "right",
    "left",
    "up",
    "down",
    "wait",
    "retry",
}
OUTCOMES = {
    "pending",
    "powered",
    "phase",
    "player",
    "recorded",
    "echo_index",
    "active_pad",
    "open_gate",
    "outcome",
    "console",
}


@dataclass(frozen=True)
class LessonStep:
    id: str
    title: str
    explanation: str
    objective: str
    action: str
    expected: dict
    target: dict


def load_steps(data: object, chamber: Chamber) -> tuple[LessonStep, ...]:
    """Older fixtures may omit guided content; malformed lessons fail explicitly."""
    if data is None:
        return ()
    if not isinstance(data, list) or not data:
        raise LevelError("tutorial_steps must be a non-empty list")
    steps = []
    ids = set()
    circuits = {c.id for c in chamber.circuits}
    pads = {p.id for p in chamber.pads}
    gates = {d.id for d in chamber.devices if d.kind.value == "gate"}
    for item in data:
        if not isinstance(item, dict):
            raise LevelError("tutorial step must be an object")
        for field in ("id", "title", "explanation", "objective", "action"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise LevelError(f"tutorial step requires {field}")
        if item["id"] in ids or item["action"] not in ACTIONS:
            raise LevelError("duplicate tutorial id or unknown action")
        ids.add(item["id"])
        expected, target = item.get("expected"), item.get("target")
        if not isinstance(expected, dict) or not expected or expected.keys() - OUTCOMES:
            raise LevelError("tutorial step requires known expected outcomes")
        for field, value in expected.items():
            if field in {"powered", "pending"}:
                if (
                    not isinstance(value, list)
                    or any(not isinstance(v, str) or v not in circuits for v in value)
                    or len(value) != len(set(value))
                ):
                    raise LevelError("tutorial references an unknown circuit")
            elif field == "player":
                if not _position(value, chamber):
                    raise LevelError("tutorial player target outside chamber")
            elif field in {"recorded", "echo_index"}:
                if type(value) is not int or not 0 <= value <= chamber.max_turns:
                    raise LevelError("tutorial recording index out of range")
            elif field == "phase" and (
                not isinstance(value, str)
                or value
                not in {
                    "prepare",
                    "recording",
                    "committed",
                    "replay",
                    "result",
                }
            ):
                raise LevelError("unknown tutorial phase")
            elif field == "outcome" and (
                not isinstance(value, str) or value not in {"accepted", "rejected"}
            ):
                raise LevelError("unknown tutorial outcome")
            elif field == "console" and type(value) is not bool:
                raise LevelError("tutorial console outcome must be boolean")
            elif field == "active_pad" and (
                not isinstance(value, str) or value not in pads
            ):
                raise LevelError("tutorial references an unknown pad")
            elif field == "open_gate" and (
                not isinstance(value, str) or value not in gates
            ):
                raise LevelError("tutorial references an unknown gate")
        if not isinstance(target, dict):
            raise LevelError("tutorial step requires a highlight target")
        kind = target.get("kind")
        valid = isinstance(kind, str) and (
            kind in {"power", "state"}
            or kind == "tile"
            and _position(target.get("position"), chamber)
            or kind == "circuit"
            and isinstance(target.get("id"), str)
            and target["id"] in circuits
            or kind == "timeline"
            and type(target.get("index")) is int
            and 0 <= target["index"] < chamber.max_turns
        )
        if not valid or (item["action"] == "toggle" and kind != "circuit"):
            raise LevelError("invalid tutorial highlight target")
        steps.append(
            LessonStep(
                **{
                    key: item[key]
                    for key in (
                        "id",
                        "title",
                        "explanation",
                        "objective",
                        "action",
                        "expected",
                        "target",
                    )
                }
            )
        )
    return tuple(steps)


def _position(value: object, chamber: Chamber) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(type(v) is int for v in value)
        and 0 <= value[0] < chamber.width
        and 0 <= value[1] < chamber.height
    )


@dataclass
class Tutorial:
    steps: tuple[LessonStep, ...]
    index: int = 0
    explaining: bool = True

    @property
    def current(self) -> LessonStep | None:
        return self.steps[self.index] if self.index < len(self.steps) else None

    def allows(self, event: str, detail: str | None = None) -> bool:
        step = self.current
        return bool(
            step
            and not self.explaining
            and step.action == event
            and (event != "toggle" or detail == step.target["id"])
        )

    def observe(
        self,
        event: str,
        state: State,
        pending: frozenset[str],
        console: bool,
        outcome: str = "accepted",
        detail: str | None = None,
    ) -> bool:
        if not self.allows(event, detail):
            return False
        actual = {
            "pending": sorted(pending),
            "powered": sorted(state.powered_circuits),
            "phase": state.phase.value,
            "player": [state.player.x, state.player.y],
            "recorded": len(state.recording),
            "echo_index": state.echo_index,
            "console": console,
            "outcome": outcome,
        }
        for key, value in self.current.expected.items():
            if key == "active_pad":
                matches = value in state.pad_active
            elif key == "open_gate":
                matches = value in state.gates_open
            else:
                matches = actual[key] == (
                    sorted(value) if key in {"pending", "powered"} else value
                )
            if not matches:
                return False
        self.index += 1
        self.explaining = True
        return True

    def rewind(self) -> None:
        """R restores launch state, so resume at the first replay action."""
        launch_index = next(
            i for i, step in enumerate(self.steps) if step.action == "launch"
        )
        self.index = launch_index + 1
        self.explaining = True
