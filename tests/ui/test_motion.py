"""Motion timelines: pure, start at the old state, end exactly on the new one."""

import ast
import copy
from dataclasses import replace
from itertools import pairwise
from pathlib import Path

import pytest

from echo_shift.engine import lighting, recording
from echo_shift.engine.loader import load
from echo_shift.engine.model import Phase, Position, initial_state
from echo_shift.engine.turn import Failed, InteractAtConsole, Move
from echo_shift.ui import motion
from echo_shift.ui.motion import Motion

ROOT = Path(__file__).resolve().parents[2]


def chamber(number):
    return load(ROOT / "levels" / f"chamber_{number:02}.json")


def lit_recording():
    """Chamber 1 with its circuit on, recording, standing in the hub."""
    c = chamber(1)
    return recording.enter(initial_state(c, frozenset({c.circuits[0].id})))


def walked():
    """The lit chamber before and after stepping right onto its pad."""
    before = lit_recording()
    return before, recording.act(before, Move(1, 0)).state


def run(m, frames):
    for _ in range(frames):
        m.tick()


A, B = Position(2, 3), Position(3, 3)


def test_motion_module_never_imports_pyxel():
    tree = ast.parse((ROOT / "src/echo_shift/ui/motion.py").read_text())
    names = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert "pyxel" not in names


def test_walk_glides_evenly_from_old_tile_to_new_in_its_length():
    assert motion.WALK_FRAMES == 15
    assert motion.slide(A, B, 0) == (A.x, A.y)
    assert motion.slide(A, B, motion.WALK_FRAMES) == (B.x, B.y)
    xs = [motion.slide(A, B, t)[0] for t in range(motion.WALK_FRAMES + 1)]
    steps = {round(b - a, 9) for a, b in pairwise(xs)}
    assert steps == {round(1 / motion.WALK_FRAMES, 9)}  # one steady speed


def test_walk_alternates_the_step_sprites():
    shown = {motion.walk_sprite("player", t) for t in range(motion.WALK_FRAMES)}
    assert shown == {"player_step_0", "player_step_1"}
    assert motion.walk_sprite("echo", 0) == "echo_step_0"


def test_nudge_leans_towards_the_wall_and_returns():
    assert motion.nudge((0, -1), 0) == (0, 0)
    assert motion.nudge((0, -1), motion.NUDGE_FRAMES) == (0, 0)
    mid = motion.nudge((0, -1), motion.NUDGE_FRAMES // 2)
    assert mid[0] == 0 and -motion.NUDGE_DISTANCE <= mid[1] < 0


@pytest.mark.parametrize(
    ("timeline", "first", "last", "length"),
    [
        (motion.spawn_sprite, "echo_spawn_0", "echo_spawn_2", motion.SPAWN_FRAMES),
        (motion.expire_sprite, "echo_expire_0", "echo_expire_2", motion.EXPIRE_FRAMES),
        (motion.elevator_sprite, "elevator_off", "elevator_on", motion.ELEVATOR_FRAMES),
    ],
)
def test_sprite_timelines_start_first_run_their_length_then_hand_over(
    timeline, first, last, length
):
    assert timeline(0) == first
    assert timeline(length - 1) in (last, "elevator_on_1")
    ended = timeline(length)
    assert ended in (None, "elevator_on")  # idle sprite / nothing / platform on


@pytest.mark.parametrize("opening", [True, False])
def test_gate_bars_slide_between_closed_and_open(opening):
    bars = ["gate_closed", "gate_mid", "gate_open"]
    bars = bars if opening else bars[::-1]
    assert motion.gate_sprite(opening, 0) == bars[0]
    assert motion.gate_sprite(opening, motion.GATE_FRAMES // 2) == "gate_mid"
    assert motion.gate_sprite(opening, motion.GATE_FRAMES) == bars[2]


@pytest.mark.parametrize("active", [True, False])
def test_pads_press_down_and_timed_pads_glow(active):
    press = ["pad_off", "pad_press", "pad_on"]
    glow = ["pad_timed_off", *(f"pad_timed_glow_{i}" for i in range(3)), "pad_timed_on"]
    for timed, names, length in (
        (False, press, motion.PAD_PRESS_FRAMES),
        (True, glow, motion.PAD_GLOW_FRAMES),
    ):
        names = names if active else names[::-1]
        assert motion.pad_sprite(active, timed, 0) == names[0]
        assert motion.pad_sprite(active, timed, length) == names[-1]
        seen = [motion.pad_sprite(active, timed, t) for t in range(length)]
        assert list(dict.fromkeys(seen)) == names  # every frame, in order


def test_effects_that_return_to_rest_end_exactly_at_rest():
    assert motion.tick_lift(0) == 0 == motion.tick_lift(motion.TICK_FRAMES)
    assert motion.tick_lift(motion.TICK_FRAMES // 2) > 0
    assert motion.shake(0) != (0, 0)
    assert motion.shake(motion.SHAKE_FRAMES) == (0, 0)
    assert motion.vignette(0) == 0 == motion.vignette(motion.VIGNETTE_FRAMES)
    assert 0 < motion.vignette(motion.VIGNETTE_FRAMES // 5) <= 1
    assert motion.light_progress(0) == 0
    assert motion.light_progress(motion.LIGHT_FRAMES) == 1
    assert motion.fade_alpha(0) == 1 and motion.fade_alpha(motion.FADE_FRAMES) == 0
    assert len(motion.burst(1)) == motion.BURST_COUNT
    assert motion.burst(motion.BURST_FRAMES) == ()


def test_blink_flips_every_given_number_of_seconds():
    half = round(0.4 * motion.FPS)
    assert motion.blink(0, 0.4) == 0 == motion.blink(half - 1, 0.4)
    assert motion.blink(half, 0.4) == 1


def test_a_step_starts_a_glide_that_ends_on_the_new_tile():
    before, after = walked()
    m = Motion()
    m.start(before, after)
    x, y, sprite = m.player(after.player)
    assert (x, y) == (before.player.x, before.player.y) and sprite == "player_step_0"
    run(m, motion.WALK_FRAMES // 2)
    assert before.player.x < m.player(after.player)[0] < after.player.x
    run(m, motion.WALK_FRAMES // 2 + 1)
    assert m.player(after.player) == (after.player.x, after.player.y, None)
    run(m, max(motion.LENGTHS.values()))
    assert not m.running
    assert m.pad("pad-a") is None  # nothing left over once it has ended


def test_timelines_have_their_documented_length():
    before, after = walked()
    m = Motion()
    m.start(before, after)
    for kind, length in motion.LENGTHS.items():
        m = Motion()
        m._add(kind)
        run(m, length - 1)
        assert m.running, kind
        m.tick()
        assert not m.running, kind


def test_snap_ends_everything_at_once():
    before, after = walked()
    m = Motion()
    m.start(before, after)
    assert m.running
    m.snap()
    assert not m.running
    assert m.player(after.player) == (after.player.x, after.player.y, None)


def test_a_new_step_ends_the_old_glide_and_starts_from_the_right_tile():
    before, after = walked()
    again = recording.act(after, Move(-1, 0)).state
    m = Motion()
    m.start(before, after)
    run(m, 3)
    m.start(after, again)
    x, y, _ = m.player(again.player)
    assert (x, y) == (after.player.x, after.player.y)  # not the old glide's tile


def test_a_refused_move_nudges_without_moving():
    before = lit_recording()
    m = Motion()
    m.start(before, before, None, (0, -1))
    run(m, motion.NUDGE_FRAMES // 2)
    x, y, _ = m.player(before.player)
    assert x == before.player.x and y < before.player.y
    run(m, motion.NUDGE_FRAMES)
    assert m.player(before.player) == (before.player.x, before.player.y, None)


def test_failure_shakes_and_reddens_then_settles():
    before = initial_state(chamber(2))
    m = Motion()
    m.start(before, before, Failed(before, "dark"))
    run(m, 1)
    assert m.shake() != (0, 0) and m.vignette() > 0
    run(m, motion.VIGNETTE_FRAMES)
    assert m.shake() == (0, 0) and m.vignette() == 0


def test_echo_appears_dissolves_and_glides():
    base = initial_state(chamber(5))
    start = replace(base, phase=Phase.COMMITTED, echo_start=Position(4, 4))
    launched = replace(
        base, phase=Phase.REPLAY, echo_start=Position(4, 4), echo_position=A
    )
    m = Motion()
    m.start(start, launched)
    assert m.echo(A)[2] == "echo_spawn_0"
    run(m, motion.SPAWN_FRAMES)
    assert m.echo(A) == (A.x, A.y, None)
    later = replace(launched, echo_position=B, echo_index=1, turns=1)
    m.start(launched, later)
    assert m.echo(B)[:2] == (A.x, A.y) and m.echo(B)[2] == "echo_step_0"
    gone = replace(later, echo_position=None, echo_index=2, turns=2)
    m.start(later, gone)
    assert m.echo(None) == (B.x, B.y, "echo_expire_0")
    run(m, motion.EXPIRE_FRAMES)
    assert m.echo(None) is None


def test_gates_elevators_and_pads_follow_the_state_difference():
    base = initial_state(chamber(5))
    opened = replace(base, gates_open=frozenset({"gate-a"}))
    m = Motion()
    m.start(base, opened)
    assert m.gate("gate-a") == "gate_closed"
    run(m, motion.GATE_FRAMES)
    assert m.gate("gate-a") is None
    m.start(opened, replace(opened, elevators_running=frozenset({"lift"})))
    assert m.elevator("lift") == "elevator_off"
    m.start(base, replace(base, pad_active=frozenset({"pad-b"})))
    assert m.pad("pad-b") == "pad_off"
    m.start(base, replace(base, pad_active=frozenset({"pad-a"})))
    assert m.pad("pad-a") == "pad_timed_off"
    m.start(base, replace(base, pad_timers=(("pad-a", 1), ("pad-b", 0))))
    assert m.tick_lift("pad-a") == 0.0
    run(m, motion.TICK_FRAMES // 2)
    assert m.tick_lift("pad-a") > 0


def test_a_power_change_fades_the_tiles_whose_light_changed():
    before = initial_state(chamber(2))
    after = recording.act(before, InteractAtConsole(frozenset({"lift-power"}))).state
    changed = lighting.lit_tiles(before) ^ lighting.lit_tiles(after)
    assert changed
    m = Motion()
    m.start(before, after)
    tile = next(iter(changed))
    was_lit, p = m.light(tile)
    assert was_lit == (tile in lighting.lit_tiles(before)) and p == 0
    assert m.light(Position(0, 0)) is None
    run(m, motion.LIGHT_FRAMES)
    assert m.light(tile) is None


def test_clear_bursts_at_the_exit():
    base = initial_state(chamber(1))
    cleared = replace(base, phase=Phase.RESULT)
    m = Motion()
    m.start(base, cleared)
    at, sparks = m.burst()
    assert at == cleared.player and sparks
    run(m, motion.BURST_FRAMES)
    assert m.burst() is None


def test_reduced_motion_shows_every_end_frame_at_once():
    before, after = walked()
    m = Motion(reduced=True)
    m.start(before, after, None, (1, 0))
    m.start(before, before, Failed(before, "dark"))
    m.fade_in()
    assert not m.running
    assert m.player(after.player) == (after.player.x, after.player.y, None)
    assert m.pad("pad-a") is None and m.shake() == (0, 0)
    assert m.vignette() == 0 and m.burst() is None and m.fade() == 0
    live = Motion()
    live.fade_in()
    live.set_reduced(True)  # turning it on mid-animation ends what is running
    assert not live.running and live.fade() == 0


def test_motion_only_reads_the_states_it_is_given():
    before, after = walked()
    snapshot = copy.deepcopy((before, after))
    m = Motion()
    m.start(before, after)
    m.player(after.player)
    assert (before, after) == snapshot
    with pytest.raises(AttributeError):
        before.player = A  # frozen, so a timeline cannot change the engine's state


def key(player, name):
    return getattr(player.fake, "KEY_" + name)


def tap(player, name):
    """One frame with the key just pressed (no release frame, no extra frames)."""
    player.pressed.add(key(player, name))
    player.held.add(key(player, name))
    player.game.update()
    player.game.draw()
    player.pressed.clear()
    player.held.clear()


def idle(player, frames):
    for _ in range(frames):
        player.game.update()
        player.game.draw()


def start(player, number=1, recording=True):
    player.game.open_level(number)
    player.press("F")
    if number == 1:
        player.press("E")  # open the console and switch the circuit on
        player.press("SPACE")
        player.press("ESCAPE")
    if recording:
        player.press("RETURN")


def test_a_move_during_a_glide_steps_the_engine_on_that_update(player):
    start(player)
    game = player.game
    first = game.state.player
    tap(player, "RIGHT")
    assert game.state.player == Position(first.x + 1, first.y)
    assert game.motion.running
    idle(player, 3)
    assert game.motion.running  # still gliding
    tap(player, "LEFT")  # input mid-glide is not lost or queued
    assert game.state.player == first
    x, y, _ = game.motion.player(game.state.player)
    assert first.x < x < first.x + 1  # the new glide starts from the tile reached
    assert y == first.y


def test_new_input_snaps_the_running_animation_before_the_step(player):
    start(player)
    game = player.game
    tap(player, "RIGHT")
    assert game.motion.running
    tap(player, "UP")  # a wall: the old glide ends, a nudge starts
    assert game.motion.player(game.state.player)[0] == game.state.player.x
    assert not any(k[0] == "slide" for k in game.motion._effects)


def test_a_refused_move_nudges_in_the_game(player):
    start(player)
    game = player.game
    tap(player, "UP")
    assert game.state.player == game.state.chamber.start
    assert game.motion.player(game.state.player)[1] < game.state.player.y


def test_reduced_motion_shows_the_end_frame_in_the_game(player):
    start(player)
    game = player.game
    game.progress.settings.reduced_motion = True
    tap(player, "RIGHT")
    assert not game.motion.running
    p = game.state.player
    assert game.motion.player(p) == (p.x, p.y, None)


def test_undo_shows_the_old_state_at_once(player):
    start(player)
    game = player.game
    tap(player, "RIGHT")
    idle(player, 2)
    tap(player, "Z")
    assert game.state.player == game.state.chamber.start
    assert not game.motion.running


def test_failure_shakes_the_room_in_the_game(player):
    start(player, 2)
    game = player.game
    tap(player, "RIGHT")  # a dark tile ends the take
    assert game.failure is not None
    idle(player, 1)
    assert game.motion.shake() != (0, 0) and game.motion.vignette() > 0
    game.progress.settings.reduced_motion = True
    idle(player, 1)
    assert game.motion.shake() == (0, 0) and game.motion.vignette() == 0


def test_a_new_screen_fades_in(player):
    game = player.game
    player.press("RETURN")  # title -> chamber list
    assert game.motion.fade() > 0
    tap(player, "RIGHT")  # input snaps the fade
    assert game.motion.fade() == 0
