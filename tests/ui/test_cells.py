"""Energy cells and live conduits in the interface: capacity, previews, text, motion."""

import copy
import json
from dataclasses import replace
from itertools import pairwise
from pathlib import Path

import pytest

from echo_shift.engine import lighting, power, recording
from echo_shift.engine.model import (
    Cell,
    Chamber,
    Circuit,
    Conduit,
    Device,
    Pad,
    Phase,
    Position,
    TileType,
    Zone,
    initial_state,
)
from echo_shift.engine.turn import Failed, Move
from echo_shift.ui import app, controls, cues, guide, motion
from echo_shift.ui.help import room_info, topics
from echo_shift.ui.hud import model
from echo_shift.ui.motion import Motion

ROOT = Path(__file__).resolve().parents[2]
CELL, LINE = Position(2, 1), Position(3, 1)
HUB = Position(1, 1)


def wing():
    """Hub with the console, a lit wing holding a cell (+2) and a conduit on `arc`,
    then a dark gap, a pad, a gate and the lift. Base capacity 3."""
    grid = [[TileType.WALL] * 9 for _ in range(3)]
    kinds = (
        TileType.WALL,
        TileType.CONSOLE,
        TileType.FLOOR,
        TileType.FLOOR,
        TileType.FLOOR,
        TileType.PAD,
        TileType.GATE,
        TileType.ELEVATOR,
        TileType.WALL,
    )
    for x, tile in enumerate(kinds):
        grid[1][x] = tile
    return Chamber(
        tiles=tuple(tuple(row) for row in grid),
        start=HUB,
        hub=frozenset({HUB}),
        consoles=frozenset({HUB}),
        capacity=3,
        zones=(
            Zone("wing", (CELL, LINE)),
            Zone("pads", (Position(5, 1), Position(6, 1), Position(7, 1))),
        ),
        circuits=(
            Circuit("lamp", 2, ("wing", "pads"), ("gate-a", "lift")),
            Circuit("aux", 3),
            Circuit("arc", 1),
        ),
        pads=(Pad("pad-a", Position(5, 1), 3),),
        devices=(
            Device("gate-a", TileType.GATE, Position(6, 1), "lamp", "pad-a"),
            Device("lift", TileType.ELEVATOR, Position(7, 1), "lamp", "pad-a"),
        ),
        exit=Position(7, 1),
        cells=(Cell("c1", CELL, 2),),
        conduits=(Conduit("line", "arc", (LINE,)),),
    )


def lit_state(*circuits):
    return initial_state(wing(), frozenset(circuits))


def taken_after_roam():
    """Step from the hub onto the cell with the wing lit."""
    state = lit_state("lamp")
    return state, recording.act(state, Move(1, 0)).state


# ---- the power bar -------------------------------------------------------------------


def test_hud_capacity_grows_with_the_cells_taken():
    before, after = taken_after_roam()
    assert (model(before).capacity, model(before).base) == (3, 3)
    assert (model(after).capacity, model(after).base) == (5, 3)
    assert model(after).capacity == power.capacity_of(after)


def test_capacity_topic_names_the_cells_and_uses_the_effective_total():
    before, after = taken_after_roam()
    power_text = {key: text for key, _, text in topics(after, frozenset())}["power"]
    assert "/5 units" in power_text and "1/1 energy cells" in power_text
    assert (
        "/3 units"
        in {key: text for key, _, text in topics(before, frozenset())}["power"]
    )


# ---- the console preview and the neighbour cues -------------------------------------


def test_console_preview_lists_conduit_tiles_a_choice_would_make_live():
    state = lit_state("lamp")
    found = cues.console_preview(state, frozenset({"lamp", "arc"}))
    assert found.live == {LINE} and found.changed
    assert cues.console_preview(state, frozenset({"lamp"})).live == frozenset()
    # Already live: nothing new to warn about.
    hot = lit_state("lamp", "arc")
    assert cues.console_preview(hot, frozenset({"lamp", "arc"})).live == frozenset()


def test_live_preview_alone_counts_as_a_change():
    state = lit_state()
    found = cues.console_preview(state, frozenset({"arc"}))
    assert found.live == {LINE} and found.changed


def test_unsafe_neighbours_outline_live_conduits_and_unlit_tiles():
    state = lit_state("lamp", "arc")
    walker = replace(state, player=CELL)
    assert cues.unsafe_neighbours(walker) == (LINE,)
    cold = replace(lit_state("lamp"), player=CELL)
    assert cues.unsafe_neighbours(cold) == ()
    dark = replace(lit_state(), player=HUB)
    assert cues.unsafe_neighbours(dark) == (CELL,)


def test_only_a_take_or_replay_warns_that_a_step_would_fail():
    state = lit_state("lamp")
    assert not cues.warns_unsafe(state)
    assert cues.warns_unsafe(recording.enter(state))


# ---- hover and guide text -------------------------------------------------------------


def test_hover_explains_an_energy_cell():
    state = lit_state("lamp")
    title, text = room_info(state, CELL)
    assert title == "ENERGY CELL"
    for phrase in (
        "+2",
        "max power",
        "capacity",
        "before a take or after saving",
        "never picks",
    ):
        assert phrase in text
    taken = replace(state, cells_taken=frozenset({"c1"}))
    title, text = room_info(taken, CELL)
    assert title != "ENERGY CELL" and "taken" in text


def test_hover_explains_live_and_idle_conduits():
    title, text = room_info(lit_state("lamp", "arc"), LINE)
    assert title == "LIVE CONDUIT" and "ARC" in text and "deadly" in text
    assert "Live" in text.split(". ")[-1]
    title, text = room_info(lit_state("lamp"), LINE)
    assert title == "CONDUIT (OFF)" and "ordinary floor" in text
    assert "Lit: safe" in text
    _, dark_text = room_info(lit_state(), LINE)
    assert "Dark: you cannot walk here freely" in dark_text


def test_guide_describes_cells_and_conduits():
    state = lit_state()
    objects = " ".join(guide.page_lines("objects", state, level=3))
    assert "ENERGY CELL" in objects and "CONDUIT" in objects
    power_page = " ".join(guide.page_lines("power", state, level=3))
    assert "energy cell" in power_page and "conduit" in power_page
    goal = " ".join(guide.page_lines("goal", state, level=3))
    assert "walk freely" in goal and "live conduit" in goal
    plain = initial_state(replace(wing(), cells=(), conduits=()))
    assert "ENERGY CELL" not in " ".join(guide.page_lines("objects", plain, level=3))


def test_new_text_names_no_keys_by_hand():
    state = lit_state("lamp", "arc")
    text = [
        line
        for page in guide.PAGE_IDS
        for line in guide.page_lines(page, state, level=3)
    ] + [detail for _, _, detail in topics(state, frozenset())]
    for line in text:
        controls.check_text(line)
        assert "{" not in line


# ---- motion ---------------------------------------------------------------------------


def run(m, frames):
    for _ in range(frames):
        m.tick()


LEAD = motion.PICKUP_LEAD
ARRIVE = motion.PICKUP_FRAMES


def test_a_pickup_sparkles_at_the_cell_once_the_player_has_arrived():
    before, after = taken_after_roam()
    m = Motion()
    m.start(before, after)
    assert m.sparkles() == []
    run(m, LEAD)
    ((at, sparks),) = m.sparkles()
    assert at == CELL and len(sparks) == motion.SPARKLE_COUNT
    assert all(1 <= spark.colour <= 15 for spark in sparks)
    run(m, motion.SPARKLE_FRAMES - 1)
    assert m.sparkles()
    m.tick()
    assert m.sparkles() == []
    assert motion.sparkle(motion.SPARKLE_FRAMES) == ()
    assert motion.sparkle(-1) == ()


def test_a_plain_step_or_an_undo_does_not_sparkle_or_fly():
    state = lit_state()
    after = recording.act(state, Move(1, 0)).state
    assert after.cells_taken == frozenset()
    m = Motion()
    m.start(state, after)
    assert m.sparkles() == [] and m.flights() == [] and m.floaters() == []
    before, taken = taken_after_roam()
    m.start(taken, before, undo=True)
    run(m, LEAD)
    assert m.sparkles() == [] and m.flights() == [] and m.resting() == frozenset()


def test_a_taken_cell_rests_on_its_tile_while_the_player_arrives():
    before, after = taken_after_roam()
    m = Motion()
    m.start(before, after)
    assert m.resting() == {CELL} and m.flights() == []
    run(m, LEAD - 1)
    assert m.resting() == {CELL}
    m.tick()
    assert m.resting() == frozenset() and len(m.flights()) == 1


def test_a_taken_cell_pops_then_flies_to_the_readout_and_ends_exactly():
    before, after = taken_after_roam()
    m = Motion()
    m.start(before, after)
    run(m, LEAD)
    ((at, first),) = m.flights()
    assert at == CELL and first.p == 0.0 and first.grow == pytest.approx(1.0)
    run(m, motion.CELL_POP_FRAMES)
    ((_, aloft),) = m.flights()
    assert aloft.p == 0.0 and aloft.grow == pytest.approx(1 + motion.CELL_POP_GROW)
    progress, sizes = [], []
    while m.flights():
        progress.append(m.flights()[0][1].p)
        sizes.append(m.flights()[0][1].grow)
        m.tick()
    assert progress == sorted(progress) and progress[-1] > 0.95
    assert sizes[-1] < 0.6 and sizes == sorted(sizes, reverse=True)
    flight = motion.CELL_POP_FRAMES + motion.CELL_FLY_FRAMES
    assert 25 <= flight <= 35 and ARRIVE == LEAD + flight
    assert (
        motion.pickup_flight(ARRIVE) is None and motion.pickup_flight(LEAD - 1) is None
    )


def test_the_plus_floats_up_from_the_tile_and_fades():
    before, after = taken_after_roam()
    m = Motion()
    m.start(before, after)
    assert m.floaters() == []
    run(m, LEAD)
    ((at, value, rise, ink),) = m.floaters()
    assert (at, value, rise, ink) == (CELL, 2, 0.0, 1.0)
    run(m, motion.PLUS_FRAMES - 1)
    ((_, _, high, faint),) = m.floaters()
    assert high > 0.6 and faint < 0.1
    m.tick()
    assert m.floaters() == []


def stepped_on(after):
    """The state after one more plain free step (back towards the hub)."""
    return recording.act(after, Move(-1, 0)).state


def test_a_later_free_step_ends_the_flyer_but_keeps_the_plus_and_the_count_up():
    before, after = taken_after_roam()
    again = stepped_on(after)
    m = Motion()
    m.start(before, after)
    run(m, LEAD + motion.CELL_POP_FRAMES + 3)  # the cell is in the air
    assert m.flights() and m.floaters()
    m.snap_input()  # the next press arrives
    m.start(after, again)
    assert m.flights() == []  # only the flyer snapped
    assert len(m.floaters()) == 1
    assert round(m.capacity(5)) == 3  # the count-up starts from the old value now
    shown = []
    while m.running:
        shown.append(m.capacity(5))
        m.tick()
    assert shown == sorted(shown) and shown[0] < 5 and shown[-1] > 4.9
    assert m.capacity(5) == 5.0  # and lands on the real value


def test_the_pulse_and_the_hop_survive_a_free_step_after_the_cell_landed():
    before, after = taken_after_roam()
    m = Motion()
    m.start(before, after)
    run(m, ARRIVE + 3)  # landed: the readout is pulsing
    assert m.capacity_pulse() > 0.0
    m.snap_input()
    m.start(after, stepped_on(after))
    assert m.capacity_pulse() > 0.0 or m.capacity_bounce() > 0.0


def test_an_undo_or_a_step_in_a_take_ends_everything_a_pickup_left():
    before, after = taken_after_roam()
    for undo in (True, False):
        m = Motion()
        m.start(before, after)
        run(m, LEAD + 2)
        m.snap_input()
        if undo:
            m.start(after, before, undo=True)
        else:
            m.start(recording.enter(after), recording.enter(stepped_on(after)))
        assert m.floaters() == [] and m.sparkles() == [] and m.flights() == []
        assert m.capacity_pulse() == 0.0 and m.capacity_bounce() == 0.0


def test_walking_over_a_cell_with_the_keys_still_shows_the_plus(player):
    game = player.game
    game.open_level(2)
    player.press("F")
    for key in ("LEFT", "LEFT", "E", "SPACE", "ESCAPE"):  # the wing lamp on
        player.press(key)
    for key in ("LEFT",) * 5 + ("UP",):
        player.press(key)
    assert game.state.player == Position(2, 3)
    player.press("UP")  # onto the cell
    assert game.state.cells_taken
    player.press("DOWN")  # the very next step
    assert game.motion.floaters(), "the +N MAX was cut off by the next step"
    assert game.motion.flights() == []
    for _ in range(motion.PLUS_FRAMES + motion.CAPACITY_FRAMES + 20):
        game.update()
        game.draw()
    assert game.motion.capacity(power.capacity_of(game.state)) == 50.0


def test_the_capacity_number_keeps_the_old_value_until_the_cell_lands():
    before, after = taken_after_roam()
    m = Motion()
    m.start(before, after)
    assert power.capacity_of(after) == 5  # the engine already has the new capacity
    shown = []
    while m.running:
        shown.append(round(m.capacity(5)))
        m.tick()
    assert shown[:ARRIVE] == [3] * ARRIVE
    ticks = shown[ARRIVE:]
    assert ticks == sorted(ticks) and set(shown) == {3, 4, 5}
    assert m.capacity(5) == 5
    assert (
        motion.capacity_value(3, 5, ARRIVE + motion.CAPACITY_TICK_FRAMES, ARRIVE) == 5
    )


def test_the_readout_pulses_and_bounces_only_after_the_cell_lands():
    before, after = taken_after_roam()
    m = Motion()
    m.start(before, after)
    run(m, ARRIVE - 1)
    assert m.capacity_pulse() == 0.0 and m.capacity_bounce() == 0.0
    run(m, motion.CAPACITY_FRAMES // 4 + 1)
    assert m.capacity_bounce() > 0.3
    run(m, motion.CAPACITY_FRAMES // 4)
    assert m.capacity_pulse() > 0.5
    run(m, motion.CAPACITY_FRAMES)
    assert m.capacity_pulse() == 0.0 and m.capacity_bounce() == 0.0 and not m.running
    assert motion.capacity_bounce(0) == 0.0
    assert motion.capacity_bounce(motion.CAPACITY_FRAMES) == pytest.approx(
        0.0, abs=1e-9
    )


def test_new_input_snaps_the_pickup_to_its_end_state():
    before, after = taken_after_roam()
    m = Motion()
    m.start(before, after)
    run(m, LEAD + 5)
    m.snap()
    assert not m.running
    assert m.flights() == [] and m.floaters() == [] and m.sparkles() == []
    assert m.resting() == frozenset() and m.capacity(5) == 5
    assert m.capacity_pulse() == 0.0 and m.capacity_bounce() == 0.0


def test_the_capacity_bar_does_not_pulse_when_it_shrinks_and_does_not_wait():
    before, after = taken_after_roam()
    m = Motion()
    m.start(after, before, undo=True)
    assert m.capacity_pulse() == 0.0 and m.capacity_bounce() == 0.0
    assert m.capacity(3) == 5  # eases down from the larger value at once
    run(m, motion.CAPACITY_TICK_FRAMES // motion.UNDO_PACE)
    assert m.capacity(3) == 3


def test_reduced_motion_shows_the_end_frames_at_once():
    before, after = taken_after_roam()
    m = Motion(reduced=True)
    m.start(before, after)
    assert m.sparkles() == [] and m.flights() == [] and m.floaters() == []
    assert m.resting() == frozenset() and m.capacity_pulse() == 0.0
    assert m.capacity(5) == 5 and not m.running
    assert m.cell_sprite() == "cell" and m.current_sprite() == "conduit_live"
    assert m.conduit_spark(LINE) is None and m.surge(LINE) == 0.0
    run(m, 500)
    assert m.cell_sprite(13) == "cell" and m.current_sprite() == "conduit_live"


def test_pickup_timelines_never_touch_the_engine_state():
    before, after = taken_after_roam()
    copies = copy.deepcopy((before, after))
    m = Motion()
    m.start(before, after)
    for _ in range(ARRIVE + motion.CAPACITY_FRAMES):
        m.sparkles(), m.flights(), m.floaters(), m.capacity(5), m.resting()
        m.tick()
    m.snap()
    assert (before, after) == copies


def test_pickup_and_capacity_stay_inside_the_documented_lengths():
    assert motion.LENGTHS["sparkle"] == motion.SPARKLE_FRAMES
    assert motion.LENGTHS["pickup"] == ARRIVE
    assert motion.LENGTHS["plus"] == motion.PLUS_FRAMES
    assert motion.LENGTHS["capacity"] == motion.CAPACITY_FRAMES
    assert motion.capacity_pulse(0) == 0.0
    assert motion.capacity_pulse(motion.CAPACITY_FRAMES) == 0.0
    before, after = taken_after_roam()
    m = Motion()
    m.start(before, after)
    frames = 0
    while m.running:
        m.tick()
        frames += 1
    assert frames == ARRIVE + motion.CAPACITY_FRAMES  # the longest part: capacity


def test_a_cell_idles_filling_its_bars_then_glints_and_never_flickers_fast():
    seen = [motion.cell_sprite(f) for f in range(motion.CELL_CYCLE)]
    assert seen[0] == "cell_charge_0" and seen[15] == "cell_charge_1"
    assert seen[30] == "cell_charge_2" and seen[45] == "cell"
    assert "cell_glint" in seen
    assert motion.cell_sprite(motion.CELL_CYCLE) == seen[0]  # loops
    changes = sum(a != b for a, b in pairwise([*seen, seen[0]]))
    flashes_per_second = changes / 2 * motion.FPS / motion.CELL_CYCLE
    assert flashes_per_second < 3
    assert Motion().cell_sprite(0) == "cell_charge_0"
    assert Motion().cell_sprite(50) == "cell"


def test_live_conduit_current_cycles_its_frames_at_the_documented_pace():
    steps = motion.CURRENT_STEP
    seen = [motion.current_sprite(f) for f in range(steps * 4)]
    assert seen[0] == "conduit_live"
    assert [seen[i * steps] for i in range(4)] == list(motion.CURRENT_SPRITES)
    assert all(len(set(seen[i * steps : (i + 1) * steps])) == 1 for i in range(4))
    assert motion.current_sprite(steps * 4) == seen[0]
    m = Motion()
    run(m, steps)
    assert m.current_sprite() == "conduit_live_1"


def test_conduit_sparks_are_seeded_short_and_rate_limited():
    tiles = [(x, y) for x in range(6) for y in range(3)]
    phases = set()
    for x, y in tiles:
        lit = [f for f in range(1200) if motion.conduit_spark(f, x, y)]
        assert lit == [f for f in range(1200) if motion.conduit_spark(f, x, y)]
        runs = [f for f in lit if f - 1 not in lit]
        assert all(b - a >= motion.SPARK_PERIOD for a, b in pairwise(runs))
        assert all(
            sum(1 for f in lit if r <= f < r + 99) <= motion.SPARK_FRAMES for r in runs
        )
        phases.add(lit[0] % motion.SPARK_PERIOD if lit else None)
        assert lit  # each tile sparks now and then
    assert len(phases) > 3  # not in step
    spark = next(
        motion.conduit_spark(f, 3, 1)
        for f in range(600)
        if motion.conduit_spark(f, 3, 1)
    )
    assert 0 < spark[0] < 1 and 0 < spark[1] < 1 and 1 <= spark[2] <= 15


def power_pair():
    """The wing with the lamp on, and the same wing with the arc conduit live too."""
    off = lit_state("lamp")
    return off, replace(off, powered_circuits=frozenset({"lamp", "arc"}))


def test_a_conduit_flashes_once_when_it_goes_live_and_only_there():
    off, live = power_pair()
    m = Motion()
    m.start(off, live)
    assert m.surge(LINE) == 1.0 and m.surge(CELL) == 0.0
    run(m, motion.SURGE_FRAMES // 2)
    assert 0 < m.surge(LINE) < 1
    run(m, motion.SURGE_FRAMES)
    assert m.surge(LINE) == 0.0 and not m.running
    assert motion.surge_level(motion.SURGE_FRAMES) == 0.0
    m.start(live, off)  # going off, or staying live, does not flash
    assert m.surge(LINE) == 0.0
    m.start(live, replace(live, turns=live.turns))
    assert m.surge(LINE) == 0.0


def test_an_undo_does_not_flash_a_conduit():
    off, live = power_pair()
    m = Motion()
    m.start(off, live, undo=True)
    assert m.surge(LINE) == 0.0


def zapped():
    state = recording.enter(replace(lit_state("lamp", "arc"), player=HUB))
    state = replace(state, phase=Phase.RECORDING, player=CELL)
    return state, recording.act(state, Move(1, 0))


def test_a_live_conduit_death_zaps_the_player_with_two_flashes_then_sparks():
    state, result = zapped()
    assert isinstance(result, Failed) and result.reason == lighting.LIVE
    m = Motion()
    m.start(state, state, result, (1, 0))
    seen = []
    while m.zap() is not None:
        at, bright, sparks = m.zap()
        assert at == LINE and sparks  # on the conduit it stepped onto
        seen.append(bright)
        m.tick()
    assert len(seen) == motion.ZAP_FRAMES
    flashes = sum(1 for a, b in pairwise([False, *seen]) if b and not a)
    assert flashes == 2 and seen[0] and not seen[motion.ZAP_BRIGHT[0][1]]
    assert motion.zap_sparks(motion.ZAP_FRAMES) == ()
    assert {spark.colour for spark in motion.zap_sparks(5)} <= {
        10,
        7,
    }  # like the conduit
    assert motion.zap_sparks(5) == motion.zap_sparks(5)  # seeded, no randomness


def test_the_shocked_player_stands_on_the_conduit_until_the_card_shows():
    state, result = zapped()
    m = Motion()
    assert m.player(CELL) == (CELL.x, CELL.y, None)
    m.start(state, state, result, (1, 0))
    assert m.player(CELL) == (LINE.x, LINE.y, None)
    run(m, motion.ZAP_CARD_WAIT - 1)
    assert m.player(CELL) == (LINE.x, LINE.y, None)
    m.tick()
    assert m.zap() is not None  # sparks go on, the room is back to how it was
    assert m.player(CELL) == (CELL.x, CELL.y, None)
    m.start(state, state, result, (1, 0))
    m.snap()
    assert m.player(CELL) == (CELL.x, CELL.y, None)
    reduced = Motion(reduced=True)
    reduced.start(state, state, result, (1, 0))
    assert reduced.player(CELL) == (CELL.x, CELL.y, None)


def test_the_failure_card_waits_only_for_the_zap_flashes():
    state, result = zapped()
    m = Motion()
    m.start(state, state, result, (1, 0))
    assert m.card_waits()
    run(m, motion.ZAP_CARD_WAIT - 1)
    assert m.card_waits()
    m.tick()
    assert not m.card_waits()
    m.start(state, state, result, (1, 0))
    m.snap()
    assert not m.card_waits() and m.zap() is None


def test_other_failures_and_reduced_motion_do_not_zap():
    state, result = zapped()
    m = Motion()
    m.start(state, state, Failed(state, lighting.UNLIT), (1, 0))
    assert m.zap() is None and not m.card_waits()
    reduced = Motion(reduced=True)
    reduced.start(state, state, result, (1, 0))
    assert reduced.zap() is None and not reduced.card_waits()


def test_flashes_never_reach_three_in_a_second():
    state, result = zapped()
    off, live = power_pair()
    m = Motion()
    starts = []
    for frame in range(600):
        if frame % 7 == 0:  # far faster than a hand can toggle
            before = m.surge(LINE)
            m.start(off if frame % 14 else live, live if frame % 14 else off)
            if m.surge(LINE) and not before > 0.95:
                starts.append((frame, 1))
        if frame % 5 == 3:
            m.start(state, state, result, (1, 0))
            zap = m.zap()
            if zap is not None and zap[1]:
                starts.append((frame, 2))
        m.tick()
    for frame in range(600 - motion.FPS):
        in_second = sum(n for f, n in starts if frame <= f < frame + motion.FPS)
        assert in_second < 3


# ---- drawing, through the real game loop with a fake canvas ---------------------------


def drawn_sprites(game):
    names = []
    game.atlas = type(
        "Atlas", (), {"draw": lambda s, name, *a, **k: names.append(name)}
    )()
    game.draw()
    return names


def show(player, state):
    game = player.game
    game.open_level(1)
    player.press("F")  # free play: a lesson's own message would replace a refusal
    game.state = state
    game.pending = state.powered_circuits
    game.draw()
    return game


def test_untaken_cells_and_conduits_are_drawn_by_sprite_id(player):
    game = show(player, lit_state("lamp"))
    names = drawn_sprites(game)
    assert any(name.startswith("cell") for name in names)
    assert "conduit_off" in names
    assert not any(name.startswith("conduit_live") for name in names)
    game = show(player, lit_state("lamp", "arc"))
    names = drawn_sprites(game)
    assert any(name.startswith("conduit_live") for name in names)
    assert "conduit_off" not in names


def test_a_taken_cell_is_not_drawn_any_more(player):
    _, taken = taken_after_roam()
    names = drawn_sprites(show(player, taken))
    assert not any(name.startswith("cell") for name in names)


def test_the_idle_cell_and_live_current_follow_the_clock_and_reduced_motion(player):
    game = show(player, lit_state("lamp", "arc"))
    phase = CELL.x * 37 + CELL.y * 91  # each cell idles out of step with the rest
    game.motion.clock = 50
    names = drawn_sprites(game)
    assert motion.cell_sprite(50 + phase) in names and "conduit_live_2" in names
    game.motion.clock = 8
    names = drawn_sprites(game)
    assert motion.cell_sprite(8 + phase) in names and "conduit_live_1" in names
    game.motion.reduced = True
    game.motion.clock = 7
    names = drawn_sprites(game)
    assert "cell" in names and "conduit_live" in names


def test_a_flying_cell_ends_on_the_readout_and_the_number_counts_up(player):
    before, after = taken_after_roam()
    game = show(player, before)
    game.draw()  # places the readout
    game.state = after
    game.motion.start(before, after)
    run(game.motion, LEAD + motion.CELL_POP_FRAMES + motion.CELL_FLY_FRAMES - 1)
    calls = []
    game.atlas = type(
        "Atlas", (), {"draw": lambda s, name, *a, **k: calls.append((name, a))}
    )()
    player.drawn.clear()
    game.draw()
    assert "POWER 2/3" in player.drawn  # still the old capacity: it has not landed
    flyers = [
        a for name, a in calls if name == "cell"
    ]  # the taken cell is the only one
    assert len(flyers) == 1
    x, y, size = flyers[0]
    tx, ty = game.power_at
    assert abs(x + size / 2 - tx) < 3 and abs(y + size / 2 - ty) < 3
    assert size >= app.FLYER_MIN  # still a readable battery on arrival
    run(game.motion, motion.CAPACITY_TICK_FRAMES + 1)
    player.drawn.clear()
    game.draw()
    assert "POWER 2/5" in player.drawn
    game.motion.snap()
    player.drawn.clear()
    game.draw()
    assert "POWER 2/5" in player.drawn  # a snap shows the real capacity


def test_the_flying_cell_never_gets_smaller_than_a_readable_battery(player):
    before, after = taken_after_roam()
    game = show(player, before)
    game.draw()
    game.state = after
    game.motion.start(before, after)
    game.shaken = (20, 100, 100)  # a scrolled camera with small tiles
    sizes = []
    game.atlas = type(
        "Atlas",
        (),
        {"draw": lambda s, name, x, y, size, *a: sizes.append((name, size))},
    )()
    for _ in range(ARRIVE):
        game.draw_flights()
        game.motion.tick()
    flying = [size for name, size in sizes if name == "cell"]
    assert flying and min(flying) >= app.FLYER_MIN


def test_the_plus_is_drawn_over_the_tile_while_it_floats(player):
    before, after = taken_after_roam()
    game = show(player, before)
    game.state = after
    game.motion.start(before, after)
    run(game.motion, LEAD + 5)
    player.drawn.clear()
    placed = []
    real_text = game.text
    game.text = lambda x, y, value, *a, **k: (
        placed.append((x, value)) or real_text(x, y, value, *a, **k)
    )
    game.draw()
    assert "+2 MAX" in player.drawn
    cell, origin_x, _ = game.room_view
    # Right of the swelling cell, so the flyer never hides it.
    assert all(
        x >= origin_x + (CELL.x + 0.7) * cell for x, v in placed if v == "+2 MAX"
    )
    game.motion.snap()
    player.drawn.clear()
    game.draw()
    assert "+2 MAX" not in player.drawn


def test_the_failure_cards_unavailable_retry_row_is_dimmed(player):
    state = recording.enter(replace(lit_state("lamp", "arc"), player=HUB))
    state = replace(state, phase=Phase.RECORDING, player=CELL)
    game = show(player, state)
    game.act(Move(1, 0))  # a take: there is no launch to retry from
    game.motion.snap()
    assert not controls.find(game.actions(), "retry").enabled
    inks = {}
    game.text = lambda x, y, value, color=7, scale=None: inks.__setitem__(value, color)
    game.draw()
    assert inks["Retry from launch"] == 13
    assert inks["Undo last move"] == 7
    assert inks["Restart chamber"] == 7


def test_the_failure_card_follows_the_zap_and_keys_still_work(player):
    state = recording.enter(replace(lit_state("lamp", "arc"), player=HUB))
    state = replace(state, phase=Phase.RECORDING, player=CELL)
    game = show(player, state)
    game.act(Move(1, 0))
    assert game.failure is not None and game.failure.reason == lighting.LIVE
    game.animate(state, game.mode)
    player.drawn.clear()
    game.draw()
    assert "ATTEMPT FAILED" not in player.drawn  # the zap shows first
    run(game.motion, motion.ZAP_CARD_WAIT)
    player.drawn.clear()
    game.draw()
    assert "ATTEMPT FAILED" in player.drawn
    game.motion.reduced = True
    game.motion.snap()
    player.drawn.clear()
    game.draw()
    assert "ATTEMPT FAILED" in player.drawn


def test_a_live_conduit_in_the_dark_is_not_dimmed(player):
    state = lit_state("arc")  # live, but the wing is unlit
    assert LINE not in lighting.lit_tiles(state)
    game = show(player, state)
    remapped, order = [False], []
    app.pyxel.pal = lambda *a: remapped.__setitem__(0, bool(a))
    game.atlas = type(
        "Atlas",
        (),
        {"draw": lambda s, name, *a, **k: order.append((name, remapped[0]))},
    )()
    game.draw()
    assert ("conduit_live", False) in order or any(
        name.startswith("conduit_live") and not dimmed for name, dimmed in order
    )
    assert ("floor_lit", True) in order  # the unlit cell tile beside it is dimmed


def test_the_console_lists_what_would_go_live(player):
    game = show(player, lit_state("lamp"))
    game.console = True
    game.pending = frozenset({"lamp", "arc"})
    shown = []
    game.draw_panel = lambda title, lines, *a, **k: shown.extend(lines)
    game.draw_console()
    assert "WILL GO LIVE: LINE" in shown
    assert any(line.startswith("PENDING LOAD 3/3") for line in shown)


def test_the_console_budget_includes_the_cells_taken(player):
    _, taken = taken_after_roam()
    game = show(player, taken)
    game.console = True
    game.pending = frozenset({"lamp", "aux"})
    shown = []
    game.draw_panel = lambda title, lines, *a, **k: shown.extend(lines)
    game.draw_console()
    assert any(line.startswith("PENDING LOAD 5/5") for line in shown)
    assert "OVER BUDGET - CANNOT APPLY" not in shown


def test_refusals_read_well(player):
    game = show(player, lit_state())
    player.press("RIGHT")  # the wing is dark: free roam refuses
    assert game.message == "TOO DARK TO WALK THERE"
    game = show(player, replace(lit_state("lamp", "arc"), player=CELL))
    player.press("RIGHT")
    assert game.message == "THAT CONDUIT IS LIVE"


# ---- the sprites are packed ------------------------------------------------------------


def test_the_new_sprites_are_in_the_atlas_and_manifest():
    atlas = json.loads((ROOT / "assets/atlas.json").read_text())
    manifest = {
        a["id"]: a
        for a in json.loads((ROOT / "assets/manifest.json").read_text())["assets"]
    }
    frames = (
        *("cell_charge_0", "cell_charge_1", "cell_charge_2", "cell_glint"),
        *(f"conduit_live_{k}" for k in (1, 2, 3)),
    )
    assert set(frames) == (set(motion.CURRENT_SPRITES) - {"conduit_live"}) | {
        "cell_charge_0",
        "cell_charge_1",
        "cell_charge_2",
        "cell_glint",
    }
    for sprite in ("cell", "conduit_off", "conduit_live", *frames):
        assert sprite in atlas
        assert manifest[sprite]["source"] == "derived"
        assert manifest[sprite]["status"] == "ok"


def test_recorded_failure_on_a_live_conduit_is_phrased_for_the_card():
    state = recording.enter(replace(lit_state("lamp", "arc"), player=HUB))
    state = replace(state, phase=Phase.RECORDING, player=CELL)
    result = recording.act(state, Move(1, 0))
    assert result.reason == lighting.LIVE
