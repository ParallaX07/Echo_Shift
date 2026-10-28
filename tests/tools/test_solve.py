import json

from echo_shift.engine.search import analyze, play
from tests.engine.test_search_cells import conduit_corridor, wing_cell
from tools import solve


def test_the_printed_steps_replay_free_roam_and_cells():
    # The walk into the wing and the power changes are spelled out as steps, in
    # the order a player would press them.
    for chamber in (wing_cell(), conduit_corridor()):
        report = analyze(chamber)
        steps = json.loads(solve.steps_json(report.trace))["steps"]
        assert steps == list(report.trace)
        exited, turns, _, _ = play(chamber, tuple(steps))
        assert exited and turns == report.turns
    trace = analyze(wing_cell()).trace
    assert "right" in trace[: trace.index("launch")]


def test_the_peak_column_says_what_it_is_measured_against(capsys):
    chamber = wing_cell()
    solve.print_table([(1, chamber, analyze(chamber))])
    out = capsys.readouterr().out
    assert "peak/max cap" in out and "4/4" in out  # capacity 2 plus a cell worth 2
