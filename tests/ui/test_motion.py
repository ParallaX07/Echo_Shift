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
from echo_shift.ui import bars, motion, pointer
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


def at_console(state):
    (console,) = state.chamber.consoles
    return replace(state, player=console)


def test_a_power_change_fades_the_tiles_whose_light_changed():
    before = at_console(initial_state(chamber(2)))
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
        player.to_console()
        player.press("E")  # open the console and switch the circuit on
        player.press("SPACE")
        player.press("ESCAPE")
        for _ in range(4):
            player.press("RIGHT")  # back to the door
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


def test_undo_plays_the_step_backwards_in_the_game(player):
    start(player)
    game = player.game
    begin = game.state.player
    tap(player, "RIGHT")
    idle(player, 2)
    tap(player, "Z")
    assert game.state.player == game.state.chamber.start  # the engine is already back
    assert game.motion.running
    x, y, _ = game.motion.player(game.state.player)
    assert x > begin.x and y == begin.y  # drawn still coming back from the tile
    idle(player, motion.WALK_FRAMES // motion.UNDO_PACE)
    assert not game.motion.running
    assert game.motion.player(game.state.player) == (begin.x, begin.y, None)


def test_undo_is_instant_with_reduced_motion_in_the_game(player):
    start(player)
    game = player.game
    tap(player, "RIGHT")
    game.progress.settings.reduced_motion = True
    idle(player, 1)
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


def test_undo_runs_the_step_back_at_double_speed():
    before, after = walked()
    m = Motion()
    m.start(after, before, undo=True)  # undoing the step from `before` to `after`
    assert m.player(before.player) == (after.player.x, after.player.y, "player_step_0")
    ticks = -(-motion.WALK_FRAMES // motion.UNDO_PACE)  # half the walk, rounded up
    run(m, ticks - 1)
    assert ("slide", "player") in m._effects
    run(m, 1)
    assert ("slide", "player") not in m._effects
    assert m.player(before.player) == (before.player.x, before.player.y, None)
    m.start(before, after)  # a forward step still takes its full length
    run(m, motion.WALK_FRAMES - 1)
    assert ("slide", "player") in m._effects


def test_undo_is_instant_with_reduced_motion():
    before, after = walked()
    m = Motion(reduced=True)
    m.start(after, before, undo=True)
    assert not m.running
    assert m.player(before.player) == (before.player.x, before.player.y, None)


def test_undoing_a_launch_does_not_spawn_an_echo():
    base = initial_state(chamber(5))
    committed = replace(base, phase=Phase.COMMITTED, echo_start=Position(4, 4))
    launched = replace(
        base, phase=Phase.REPLAY, echo_start=Position(4, 4), echo_position=A
    )
    m = Motion()
    m.start(launched, committed, undo=True)
    assert m.echo(None) is None
    assert not any(k[0] in ("spawn", "expire") for k in m._effects)


def test_a_filled_slot_pops_then_settles():
    before, after = walked()
    m = Motion()
    m.start(before, after)
    assert m.pop(0) == 1.0  # starts at its resting size
    run(m, motion.POP_FRAMES // 2)
    assert m.pop(0) > 1.0 and m.pop(1) == 1.0
    run(m, motion.POP_FRAMES)
    assert m.pop(0) == 1.0 and ("pop", 0) not in m._effects
    m.start(after, before, undo=True)
    assert m.pop(0) == 1.0  # an undo does not pop


def test_the_playback_slot_pulses_and_returns_each_period():
    assert motion.pulse(0) == 0 == motion.pulse(motion.PULSE_FRAMES)
    assert motion.pulse(motion.PULSE_FRAMES // 2) == 1.0
    assert Motion(reduced=True).pulse() == 0.0
    live = Motion()
    run(live, motion.PULSE_FRAMES // 2)
    assert live.pulse() == 1.0


def test_the_power_bar_eases_from_the_old_load_to_the_new_one():
    before = at_console(initial_state(chamber(2)))
    after = recording.act(before, InteractAtConsole(frozenset({"lift-power"}))).state
    old, new = motion._load(before), motion._load(after)
    assert old != new
    m = Motion()
    m.start(before, after)
    assert m.power_load(new) == old
    run(m, motion.POWER_FRAMES // 2)
    assert min(old, new) < m.power_load(new) < max(old, new)
    run(m, motion.POWER_FRAMES)
    assert m.power_load(new) == new and not m.running
    still = Motion(reduced=True)
    still.start(before, after)
    assert still.power_load(new) == new


@pytest.mark.parametrize("opening", [True, False])
def test_the_console_drawer_slides_over_its_length(opening):
    m = Motion()
    if not opening:
        m.set_drawer(True, animate=False)
    m.set_drawer(opening)
    first = m.drawer_hidden()
    assert first == (1.0 if opening else 0.0)
    run(m, motion.DRAWER_FRAMES // 2)
    assert 0.0 < m.drawer_hidden() < 1.0
    run(m, motion.DRAWER_FRAMES // 2 - 1)
    assert m.drawer_hidden() is not None
    m.tick()
    assert m.drawer_hidden() is None and not m.running


def test_the_drawer_is_instant_with_reduced_motion_or_on_a_new_screen():
    still = Motion(reduced=True)
    still.set_drawer(True)
    assert still.drawer_hidden() is None
    quiet = Motion()
    quiet.set_drawer(True, animate=False)
    assert quiet.drawer_hidden() is None
    quiet.set_drawer(False)  # a later change still slides
    assert quiet.drawer_hidden() == 0.0


def button(key):
    return bars.Item("button", key, (0, 0, 10, 10), "x")


def test_new_and_vanished_buttons_slide_and_the_first_sight_does_not():
    m = Motion()
    a, b = button("action:a"), button("action:b")
    m.sync_buttons({a.key: a})
    assert not m.running  # the bar as first shown is not "new"
    m.sync_buttons({a.key: a, b.key: b})
    assert m.button_hidden(b.key) == 1.0 and m.button_hidden(a.key) is None
    run(m, motion.BUTTON_FRAMES // 2)
    assert 0.0 < m.button_hidden(b.key) < 1.0
    run(m, motion.BUTTON_FRAMES)
    assert m.button_hidden(b.key) is None
    m.sync_buttons({a.key: a})
    [(gone, hidden)] = m.leaving_buttons()
    assert gone == b and hidden == 0.0
    run(m, motion.BUTTON_FRAMES)
    assert m.leaving_buttons() == []
    m.fade_in()  # a new screen starts from a fresh baseline
    m.sync_buttons({})
    assert m.leaving_buttons() == []


def test_buttons_do_not_slide_with_reduced_motion():
    m = Motion(reduced=True)
    m.sync_buttons({})
    m.sync_buttons({"action:a": button("action:a")})
    assert not m.running and m.button_hidden("action:a") is None


def test_the_idle_bob_is_one_sprite_pixel_and_off_with_reduced_motion():
    bobs = {motion.breath(f) for f in range(motion.FPS * 2)}
    assert bobs == {0.0, 1 / motion.SPRITE_PX}
    live = Motion()
    run(live, round(motion.BREATH_SECONDS * motion.FPS))
    assert live.breath() == 1 / motion.SPRITE_PX
    assert Motion(reduced=True).breath() == 0.0


def test_dust_is_deterministic_sparse_in_palette_and_off_with_reduced_motion():
    seen = [motion.dust(f) for f in range(motion.DUST_LIFE * 2)]
    assert seen == [motion.dust(f) for f in range(motion.DUST_LIFE * 2)]
    assert all(len(motes) <= motion.DUST_COUNT for motes in seen)
    colours = {mote.colour for motes in seen for mote in motes}
    assert colours and colours <= {5, 6, 13}
    assert all(0 <= mote.x <= 1 and 0 <= mote.y <= 1 for m in seen for mote in m)
    live = Motion()
    run(live, 30)
    assert live.dust() == motion.dust(30)
    assert Motion(reduced=True).dust() == ()


def test_the_console_flickers_rarely_and_not_with_reduced_motion():
    lit = [motion.console_lit(f) for f in range(motion.FPS * 20)]
    assert any(lit) and not all(lit)
    for first in range(len(lit) - motion.FPS):
        window = lit[first : first + motion.FPS]
        flashes = sum(1 for a, b in pairwise([False, *window]) if b and not a)
        assert flashes < 3
    assert not Motion(reduced=True).console_lit()


def test_conduit_pulse_travels_the_rails_and_wraps():
    assert motion.conduit(0) == 0
    assert 0 < motion.conduit(motion.CONDUIT_FRAMES // 2) < 1
    assert motion.conduit(motion.CONDUIT_FRAMES) == 0
    assert Motion(reduced=True).conduit() is None


def test_the_echo_leaves_a_short_dim_trail_of_where_it_was():
    base = initial_state(chamber(5))
    path = [Position(2 + i, 3) for i in range(6)]
    launched = replace(
        base, phase=Phase.REPLAY, echo_start=path[0], echo_position=path[0]
    )
    m = Motion()
    m.start(replace(launched, phase=Phase.COMMITTED), launched)
    assert m.trail(path[0]) == ()
    state = launched
    for i in range(1, 5):
        step = replace(state, echo_position=path[i], echo_index=i, turns=i)
        m.start(state, step)
        state = step
    assert m.trail(path[4]) == (path[3], path[2], path[1])  # newest first, 3 kept
    assert m.trail(None) == ()
    assert len(motion.TRAIL_ALPHA) == motion.TRAIL_LENGTH
    m.set_reduced(True)
    assert m.trail(path[4]) == ()
    m.set_reduced(False)
    assert m.trail(path[4]) == ()  # reduced motion dropped it


def test_a_new_launch_starts_a_fresh_trail():
    base = initial_state(chamber(5))
    one = replace(base, phase=Phase.REPLAY, echo_start=A, echo_position=A)
    two = replace(one, echo_position=B, echo_index=1, turns=1)
    m = Motion()
    m.start(one, two)
    assert m.trail(B) == (A,)
    m.start(replace(one, phase=Phase.COMMITTED), one)  # launched again
    assert m.trail(B) == ()


def hold(player, name, frames):
    """Hold a key for `frames` updates; return the player's tile after each."""
    code = key(player, name)
    player.held.add(code)
    tiles = []
    for index in range(frames):
        if index == 0:
            player.pressed.add(code)
        player.game.update()
        player.game.draw()
        player.pressed.discard(code)
        tiles.append(player.game.state.player)
    player.held.discard(code)
    return tiles


def changes(tiles, first):
    """The frames on which the tile changed."""
    now, frames = first, []
    for frame, tile in enumerate(tiles):
        if tile != now:
            frames.append(frame)
            now = tile
    return frames


@pytest.mark.parametrize("reduced", [False, True])
def test_a_held_key_steps_at_once_then_as_each_glide_lands(player, reduced):
    start(player)
    game = player.game
    game.progress.settings.reduced_motion = reduced
    first = game.state.player
    tiles = hold(player, "RIGHT", motion.WALK_FRAMES * 2 + 5)
    assert changes(tiles, first) == [0, motion.WALK_FRAMES]
    assert tiles[0] == Position(first.x + 1, first.y)


def test_holding_does_not_cut_the_glide_short(player):
    start(player)
    game = player.game
    first = game.state.player
    code = key(player, "RIGHT")
    player.held.add(code)
    player.pressed.add(code)
    xs = []
    for _ in range(motion.WALK_FRAMES):
        game.update()
        game.draw()
        player.pressed.discard(code)
        xs.append(game.motion.player(game.state.player)[0])
    player.held.discard(code)
    assert game.state.player.x == first.x + 1  # one step only so far
    assert xs[: motion.WALK_FRAMES - 1] == sorted(set(xs[:-1]))  # steadily advancing
    assert first.x < xs[motion.WALK_FRAMES // 2] < first.x + 1


def test_a_held_key_asks_once_and_stops_after_a_refused_step(player):
    start(player)
    game = player.game
    code = key(player, "UP")
    player.held.add(code)
    player.pressed.add(code)
    left = []
    for _ in range(motion.WALK_FRAMES * 4):
        game.update()
        game.draw()
        player.pressed.discard(code)
        left.append(game.message_frames)
    assert game.message_error and game.walker.action is None
    assert left == sorted(left, reverse=True)  # never told again while held
    assert len(game.state.recording) == 0


def test_a_held_key_stops_when_the_take_fails(player):
    start(player, 2)
    game = player.game
    hold(player, "RIGHT", 2)  # a dark tile ends the take
    assert game.failure is not None and game.walker.action is None


def test_a_held_key_stops_when_the_recording_is_full(player):
    start(player)
    game = player.game
    for _ in range(game.state.chamber.max_turns - 1):
        player.press("SPACE")
    tiles = hold(player, "RIGHT", motion.WALK_FRAMES * 3)
    assert len(changes(tiles, game.state.chamber.start)) == 1  # the last turn only
    assert len(game.state.recording) == game.state.chamber.max_turns
    idle(player, 1)
    tap(player, "RIGHT")  # one fresh press still explains the refusal
    assert "RECORDING FULL" in game.message


def test_releasing_and_pressing_again_steps_at_once(player):
    start(player)
    game = player.game
    hold(player, "RIGHT", 4)
    assert game.walker.action == "move_right"
    idle(player, 1)
    assert game.walker.action is None  # released
    before = game.state.player
    tap(player, "LEFT")
    assert game.state.player == Position(before.x - 1, before.y)


def test_walker_waits_a_full_walk_and_ends_on_anything_else():
    walker = motion.Walker()
    walker.stepped("a", True)
    for _ in range(motion.WALK_FRAMES):
        assert not walker.repeats("a", True, True)
        walker.tick(True)
    assert walker.repeats("a", True, True)
    assert not walker.repeats("b", True, True)  # only its own direction repeats
    assert not walker.repeats("a", True, False)  # a disabled move ends the walk
    assert walker.action is None
    walker.stepped("a", False)  # a refused step is never repeated
    walker.tick(True)
    assert walker.action is None
    walker.stepped("a", True)
    walker.tick(False)  # play input did not run (a menu opened, ...)
    assert walker.action is None


def test_the_console_drawer_slides_but_its_rows_stay_where_they_rest(player):
    game = player.game
    game.open_level(1)
    player.press("F")
    player.to_console()
    tap(player, "E")
    assert game.console
    hidden = game.motion.drawer_hidden()
    assert hidden is not None and 0 < hidden < 1
    game.draw()
    rows = [rect for rect, key_ in game.ui_hits if key_.startswith("row:")]
    assert rows and all(r[0] >= game.layout.console_drawer()[0] for r in rows)
    idle(player, motion.DRAWER_FRAMES)
    assert game.motion.drawer_hidden() is None
    tap(player, "ESCAPE")
    assert not game.console
    assert game.motion.drawer_hidden() is not None  # still sliding out
    game.draw()
    assert not any(key_.startswith("row:") for _, key_ in game.ui_hits)
    idle(player, motion.DRAWER_FRAMES)
    assert game.motion.drawer_hidden() is None


def test_tiles_under_a_sliding_drawer_are_not_hit_but_those_beside_it_are(player):
    game = player.game
    game.open_level(1)
    player.press("F")
    player.to_console()
    tap(player, "E")
    tap(player, "ESCAPE")  # the drawer is sliding out; the console flag is off
    hidden = game.motion.drawer_hidden()
    assert not game.console and hidden is not None and hidden > 0
    game.draw()
    x, _, width, _ = game.layout.console_drawer()
    edge = x + round(hidden * width)
    y = game.layout.room_y + game.layout.room_h // 2
    bounds = game.room_bounds
    for px, hit in ((edge - 1, True), (edge, False), (edge + width // 2, False)):
        player.fake.mouse_x, player.fake.mouse_y = px, y
        free = pointer.tile_at(game.shaken, bounds, game.layout.room, px, y)
        assert free is not None, px  # the world reaches under the strip
        assert (game.pointer_tile(game.shaken) is not None) is hit, px
    player.fake.mouse_x = player.fake.mouse_y = -1


def test_a_button_that_leaves_the_bar_sinks_without_a_hit_rect(player):
    start(player)
    game = player.game
    game.draw()
    ghost = button("action:ghost")
    game.motion._buttons["action:ghost"] = ghost
    game.draw()
    assert [item for item, _ in game.motion.leaving_buttons()] == [ghost]
    assert "action:ghost" not in [key_ for _, key_ in game.ui_hits]
