"""Goals on the result card, in the save and on the level select."""

import json
from dataclasses import replace
from pathlib import Path

from echo_shift.engine.loader import load
from echo_shift.engine.model import Goals
from echo_shift.engine.turn import InteractAtConsole, Move, Wait
from echo_shift.ui import goals, progress

LEVELS = Path(__file__).resolve().parents[2] / "levels"
MOVES = {
    "up": Move(0, -1),
    "right": Move(1, 0),
    "down": Move(0, 1),
    "left": Move(-1, 0),
    "wait": Wait(),
}


# Chamber 3's goals, read from its level file so a re-tuned chamber needs no edit.
CHAMBER_3 = load(LEVELS / "chamber_03.json")
TURNS, RECORDED = CHAMBER_3.goals.turns, CHAMBER_3.goals.recorded
LIMIT = CHAMBER_3.max_turns


def trace(number, kind="turns"):
    path = LEVELS / "solutions" / f"chamber_{number:02}.goals.json"
    return json.loads(path.read_text())[kind]


def solution(number):
    path = LEVELS / "solutions" / f"chamber_{number:02}.json"
    return json.loads(path.read_text())["steps"]


def start(player, number):
    game = player.game
    game.open_level(number)
    game.modal = None
    return game


def perform(game, steps):
    """Feed trace tokens through the game's own input paths."""
    for token in steps:
        if isinstance(token, dict):
            game.act(InteractAtConsole(frozenset(token["power"])))
        elif token in ("enter", "launch"):
            game.echo_key()
        else:
            game.act(MOVES[token])


def saved(player):
    return progress.load(3, player.directory)


# ---- the run is measured the way the solver measures a play ------------------


def test_goal_run_meets_both_goals_and_shows_them_on_the_card(player):
    game = start(player, 3)
    perform(game, trace(3))
    assert game.modal == "result"
    assert game.run == goals.Run(TURNS, RECORDED, Goals(TURNS, RECORDED), LIMIT)
    assert game.run.lines() == [
        f"TURNS: {TURNS} / GOAL {TURNS} MET",
        f"RECORDED: {RECORDED} / GOAL {RECORDED} MET",
    ]
    player.drawn.clear()
    game.draw()
    text = " ".join(player.drawn)
    assert f"TURNS: {TURNS}" in text and f"GOAL {TURNS}" in text
    assert f"RECORDED: {RECORDED}" in text
    assert saved(player).goals["3"] == {"turns": True, "recorded": True}


def slower(steps):
    """The solution with one more wait recorded, a turn and a command too many."""
    at = steps.index("wait")
    return [*steps[: at + 1], "wait", *steps[at + 1 :]]


def test_a_slower_run_shows_its_misses_and_saves_no_goal(player):
    game = start(player, 3)
    perform(game, slower(solution(3)))
    assert game.run == goals.Run(TURNS + 1, RECORDED + 1, Goals(TURNS, RECORDED), LIMIT)
    assert game.run.lines() == [
        f"TURNS: {TURNS + 1} / GOAL {TURNS} NOT MET",
        f"RECORDED: {RECORDED + 1} / GOAL {RECORDED} NOT MET",
    ]
    assert saved(player).goals["3"] == {"turns": False, "recorded": False}


def test_goals_are_only_ever_upgraded(player):
    game = start(player, 3)
    perform(game, trace(3))
    start(player, 3)
    perform(game, slower(solution(3)))  # a worse clear afterwards
    assert game.run.turns_met is False
    assert saved(player).goals["3"] == {"turns": True, "recorded": True}


def test_goals_never_gate_unlocking(player):
    game = start(player, 1)
    steps = solution(1)
    cut = steps.index("launch") + 1
    perform(game, [*steps[:cut], "wait", *steps[cut:]])  # one turn too slow
    assert game.modal == "result" and game.run.turns_met is False
    assert game.unlocked == 2
    assert saved(player).unlocked == 2


def test_a_retry_does_not_add_turns(player):
    game = start(player, 3)
    steps = trace(3)
    launch_at = steps.index("launch") + 1
    perform(game, steps[:launch_at])
    launched = game.state.turns
    # The lights go out under the echo's player (as if switched at the console).
    game.state = replace(game.state, powered_circuits=frozenset())
    perform(game, ["right"])  # step into the dark
    assert game.failure is not None
    game.update()  # the card ignores keys until the failing key is released
    player.press("R")  # retry from launch
    assert game.failure is None and game.state.turns == launched
    perform(game, steps[launch_at:])
    assert game.run.turns == TURNS and game.run.turns_met


def test_a_failed_take_does_not_inflate_the_next_one(player):
    game = start(player, 3)
    perform(game, ["enter", "right"])  # the route is dark, so the take fails
    assert game.failure is not None
    game.update()
    player.press("RETURN")  # accept the discarded take
    perform(game, trace(3))
    assert game.run.turns == TURNS


def test_undo_keeps_the_count_consistent(player):
    game = start(player, 3)
    steps = trace(3)
    cut = len(steps) - 6  # the six walking moves after the launch
    perform(game, steps[:cut])
    before = game.state.turns
    player.press("RIGHT")
    assert game.state.turns == before + 1
    player.press("Z")
    assert game.state.turns == before
    perform(game, steps[cut:])
    assert game.run.turns == TURNS and game.run.recorded == RECORDED


# ---- the level select ---------------------------------------------------------


def test_marks_follow_the_save_and_the_chamber_goals():
    targets = {1: goals.Target(Goals(2, 0), 6), 2: goals.Target(Goals(3, 0), 6)}
    fresh = progress.Progress()
    assert goals.marks(fresh, 1, targets) == (("C", False), ("T", False), ("R", False))
    assert goals.marks(fresh, 3, targets) == (("C", False),)  # no goals set
    played = progress.Progress(unlocked=2, goals={"1": {"turns": True}})
    assert goals.marks(played, 1, targets) == (("C", True), ("T", True), ("R", False))
    assert goals.marks(played, 2, targets)[0] == ("C", False)
    finished = progress.Progress(unlocked=3, goals={"3": {}})
    assert goals.marks(finished, 3, {})[0] == ("C", True)


def test_a_recording_goal_equal_to_the_limit_is_left_off_the_marks():
    found = goals.targets(LEVELS, 6)
    fresh = progress.Progress(unlocked=6)
    assert [letter for letter, _ in goals.marks(fresh, 3, found)] == ["C", "T", "R"]
    for number in (4, 5, 6):
        assert found[number].goals.recorded == found[number].max_turns
        assert [letter for letter, _ in goals.marks(fresh, number, found)] == [
            "C",
            "T",
        ]


def test_a_recording_goal_equal_to_the_limit_leaves_the_result_card_and_save(player):
    run = goals.Run(5, 4, Goals(5, 4), 4)
    assert run.lines() == ["TURNS: 5 / GOAL 5 MET", "RECORDED: 4"]
    assert run.recorded_met is False
    state = progress.Progress()
    assert goals.record(state, 4, run) is True
    assert state.goals["4"] == {"turns": True, "recorded": False}
    assert goals.Run(5, 3, Goals(5, 3), 4).lines()[1] == "RECORDED: 3 / GOAL 3 MET"


def test_targets_come_from_the_level_files():
    found = goals.targets(LEVELS, 8)  # chambers that do not exist are skipped
    assert sorted(found) == [1, 2, 3, 4, 5, 6]
    assert found[3] == goals.Target(Goals(TURNS, RECORDED), LIMIT)
    assert found[6].goals == Goals(16, 7)


def test_level_select_draws_the_marks(player):
    game = player.game
    game.progress.unlocked = 3
    progress.record_goals(game.progress, 1, turns=True, recorded=False)
    game.mode = "levels"
    player.drawn.clear()
    game.draw()
    assert {"C", "T", "R"} <= set(player.drawn)


def test_locked_cards_show_no_marks(player):
    game = player.game
    game.mode = "levels"
    player.drawn.clear()
    game.draw()
    assert player.drawn.count("T") == 1  # only the open chamber has marks
