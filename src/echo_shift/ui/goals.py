"""What a clearing run cost, which goals it met and what the level card shows.

Pyxel-free. A run is measured the way the solver measures a play: `turns` is the
turn-consuming actions spent on the saved take plus the turns of the launch that
reached the exit, and `recorded` is the length of the saved recording. Retries
and discarded takes cost nothing.
"""

from dataclasses import dataclass
from pathlib import Path

from echo_shift.engine.loader import load
from echo_shift.engine.model import Goals, State
from echo_shift.ui import progress as saves
from echo_shift.ui.progress import Progress


def recorded_matters(goals: Goals, max_turns: int | None) -> bool:
    """Whether the recording goal can be missed.

    A goal equal to the chamber's recording limit is met by any clear, so it
    is neither shown nor saved.
    """
    return max_turns is None or goals.recorded < max_turns


@dataclass(frozen=True)
class Run:
    turns: int
    recorded: int
    goals: Goals | None = None
    max_turns: int | None = None

    @property
    def turns_met(self) -> bool:
        return self.goals is not None and self.turns <= self.goals.turns

    @property
    def recorded_shown(self) -> bool:
        return self.goals is not None and recorded_matters(self.goals, self.max_turns)

    @property
    def recorded_met(self) -> bool:
        return self.recorded_shown and self.recorded <= self.goals.recorded

    def lines(self) -> list[str]:
        """The result-card lines: the run's cost and, when set, each target."""
        if self.goals is None:
            return [f"TURNS: {self.turns}", f"RECORDED: {self.recorded}"]
        lines = [
            f"TURNS: {self.turns} / GOAL {self.goals.turns} "
            + ("MET" if self.turns_met else "NOT MET")
        ]
        if self.recorded_shown:
            lines.append(
                f"RECORDED: {self.recorded} / GOAL {self.goals.recorded} "
                + ("MET" if self.recorded_met else "NOT MET")
            )
        else:
            lines.append(f"RECORDED: {self.recorded}")
        return lines


def run_of(state: State) -> Run:
    chamber = state.chamber
    return Run(state.turns, len(state.recording), chamber.goals, chamber.max_turns)


def record(progress: Progress, number: int, run: Run) -> bool:
    """Save the clear and its goals; True when the save changed."""
    return saves.record_goals(
        progress, number, turns=run.turns_met, recorded=run.recorded_met
    )


@dataclass(frozen=True)
class Target:
    goals: Goals
    max_turns: int


def targets(levels: Path, count: int) -> dict[int, Target]:
    """Goals of each chamber that has them, for the level select."""
    found = {}
    for number in range(1, count + 1):
        path = levels / f"chamber_{number:02}.json"
        if path.exists():
            chamber = load(path)
            if chamber.goals is not None:
                found[number] = Target(chamber.goals, chamber.max_turns)
    return found


def marks(
    progress: Progress, number: int, found: dict[int, Target]
) -> tuple[tuple[str, bool], ...]:
    """Up to three level-card marks: C cleared, T turn goal, R recording goal.

    R is left off a chamber whose recording goal every clear meets.
    """
    earned = progress.goals.get(str(number), {})
    shown = [("C", saves.cleared(progress, number))]
    if number in found:
        shown.append(("T", earned.get("turns", False)))
        target = found[number]
        if recorded_matters(target.goals, target.max_turns):
            shown.append(("R", earned.get("recorded", False)))
    return tuple(shown)
