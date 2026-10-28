"""Solve chambers with the real engine and print their difficulty report.

    uv run python tools/solve.py 3            report and shortest trace for chamber 3
    uv run python tools/solve.py --all        difficulty table for every chamber
    uv run python tools/solve.py 3 --write-goals   write levels/solutions/chamber_03.goals.json

Exit status is 1 when a chamber is unsolvable, a search hits its cap (inconclusive)
or a goal stored in the level file differs from the solver's optimum.
"""

import argparse
import json
import sys
from pathlib import Path

from echo_shift.engine.loader import load
from echo_shift.engine.model import Chamber
from echo_shift.engine.power import max_capacity
from echo_shift.engine.search import (
    DEFAULT_MAX_STATES,
    Report,
    Verdict,
    analyze,
    play,
)

LEVELS = Path(__file__).resolve().parents[1] / "levels"


def chamber_numbers() -> list[int]:
    return sorted(
        int(path.stem[-2:]) for path in LEVELS.glob("chamber_[0-9][0-9].json")
    )


def goal_problem(chamber: Chamber, report: Report) -> str | None:
    """Why the stored goals differ from the solver's optimum, if they do."""
    if chamber.goals is None or report.verdict is not Verdict.SOLVABLE:
        return None
    found = (report.turns, report.recorded)
    stored = (chamber.goals.turns, chamber.goals.recorded)
    if found != stored:
        return f"stored goals {stored} differ from solver optimum {found}"
    return None


def solve(number: int, args: argparse.Namespace) -> tuple[Chamber, Report]:
    chamber = load(LEVELS / f"chamber_{number:02}.json")
    report = analyze(
        chamber,
        max_states=args.max_states,
        max_seconds=args.max_seconds,
        solution_cap=args.solution_cap,
        idea_horizon=args.horizon,
    )
    return chamber, report


def steps_json(trace: tuple) -> str:
    return json.dumps({"steps": list(trace)})


def count_text(report: Report) -> str:
    return f">={report.solutions}" if report.solutions_capped else str(report.solutions)


def idea_text(report: Report) -> str:
    if report.idea is None:
        return "-"
    return f"{report.idea}: " + ("AVOIDABLE" if report.avoids_idea else "required")


def print_report(number: int, chamber: Chamber, report: Report) -> None:
    print(f"chamber {number:02}")
    if report.verdict is not Verdict.SOLVABLE:
        print(f"  {report.verdict.value.upper()} {report.reason}".rstrip())
        return
    print(f"  fewest turns        {report.turns}")
    print(f"  fewest recorded     {report.recorded} (in {report.recorded_turns} turns)")
    print(
        f"  lowest peak load    {report.peak_load} of {max_capacity(chamber)}"
        + (" max capacity, every cell taken" if chamber.cells else "")
    )
    print(f"  shortest solutions  {count_text(report)}")
    print(f"  taught idea         {idea_text(report)}")
    goals = chamber.goals
    print(
        "  goals               "
        + (
            f"{goals.turns} turns, {goals.recorded} recorded"
            if goals
            else "none stored"
        )
    )
    print(f"  shortest trace      {steps_json(report.trace)}")
    if report.recorded_trace != report.trace:
        print(f"  fewest-recorded     {steps_json(report.recorded_trace)}")


def print_table(rows: list[tuple[int, Chamber, Report]]) -> None:
    head = (
        "chamber",
        "idea",
        "turns",
        "recorded",
        "peak/max cap",
        "solutions",
        "idea skipped",
        "goals",
    )
    lines = [head]
    for number, chamber, report in rows:
        if report.verdict is not Verdict.SOLVABLE:
            lines.append((f"{number:02}", chamber.idea or "-", report.verdict.value))
            continue
        skipped = (
            "-" if report.avoids_idea is None else "YES" if report.avoids_idea else "no"
        )
        goals = (
            "-"
            if chamber.goals is None
            else f"{chamber.goals.turns}/{chamber.goals.recorded}"
        )
        lines.append(
            (
                f"{number:02}",
                chamber.idea or "-",
                str(report.turns),
                f"{report.recorded} ({report.recorded_turns}t)",
                f"{report.peak_load}/{max_capacity(chamber)}",
                count_text(report),
                skipped,
                goals,
            )
        )
    widths = [max(len(line[i]) for line in lines if i < len(line)) for i in range(8)]
    for line in lines:
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(line)).rstrip())


def write_goals(number: int, report: Report) -> Path:
    path = LEVELS / "solutions" / f"chamber_{number:02}.goals.json"
    record = {"turns": list(report.trace), "recorded": list(report.recorded_trace)}
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("chambers", nargs="*", type=int)
    parser.add_argument("--all", action="store_true", help="difficulty table")
    parser.add_argument("--max-states", type=int, default=DEFAULT_MAX_STATES)
    parser.add_argument("--max-seconds", type=float, default=None)
    parser.add_argument("--solution-cap", type=int, default=1000)
    parser.add_argument(
        "--horizon", type=int, default=None, help="limit idea checks to N turns"
    )
    parser.add_argument(
        "--write-goals", action="store_true", help="store the goal traces"
    )
    args = parser.parse_args()
    numbers = chamber_numbers() if args.all else args.chambers
    if not numbers:
        parser.error("name a chamber or pass --all")
    rows, problems = [], []
    for number in numbers:
        chamber, report = solve(number, args)
        rows.append((number, chamber, report))
        if report.verdict is not Verdict.SOLVABLE:
            problems.append(f"chamber {number:02}: {report.verdict.value}")
            continue
        checks = (
            (report.trace, report.turns, None),
            (report.recorded_trace, report.recorded_turns, report.recorded),
        )
        for trace, turns, recorded in checks:
            exited, spent, kept, _ = play(chamber, trace)
            if not exited or spent != turns or recorded not in (None, kept):
                problems.append(f"chamber {number:02}: a printed trace does not replay")
        mismatch = goal_problem(chamber, report)
        if mismatch:
            problems.append(f"chamber {number:02}: {mismatch}")
        if args.write_goals:
            print(f"wrote {write_goals(number, report)}")
    if args.all:
        print_table(rows)
    else:
        for number, chamber, report in rows:
            print_report(number, chamber, report)
    for problem in problems:
        print(f"PROBLEM {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
