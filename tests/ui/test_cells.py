"""Energy cells and live conduits in the interface: capacity, previews, text, motion."""

import json
from dataclasses import replace
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
from echo_shift.engine.turn import Move
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
    for phrase in ("+2", "capacity", "before a take or after saving", "never picks"):
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


def test_a_pickup_sparkles_at_the_cell_then_ends_exactly():
    before, after = taken_after_roam()
    m = Motion()
    m.start(before, after)
    ((at, sparks),) = m.sparkles()
    assert at == CELL and len(sparks) == motion.SPARKLE_COUNT
    assert all(1 <= spark.colour <= 15 for spark in sparks)
    run(m, motion.SPARKLE_FRAMES - 1)
    assert m.sparkles()
    m.tick()
    assert m.sparkles() == []
    assert motion.sparkle(motion.SPARKLE_FRAMES) == ()


def test_a_plain_step_or_an_undo_does_not_sparkle():
    state = lit_state()
    after = recording.act(state, Move(1, 0)).state
    assert after.cells_taken == frozenset()
    m = Motion()
    m.start(state, after)
    assert m.sparkles() == []
    before, taken = taken_after_roam()
    m.start(taken, before, undo=True)
    assert m.sparkles() == []


def test_the_capacity_bar_eases_and_pulses_when_it_grows():
    before, after = taken_after_roam()
    m = Motion()
    m.start(before, after)
    assert m.capacity(5) == 3
    assert m.capacity_pulse() == 0.0
    run(m, motion.CAPACITY_FRAMES // 2)
    assert m.capacity(5) == 5
    assert m.capacity_pulse() == pytest.approx(1.0, abs=0.1)
    run(m, motion.CAPACITY_FRAMES)
    assert m.capacity_pulse() == 0.0 and not m.running


def test_the_capacity_bar_does_not_pulse_when_it_shrinks():
    before, after = taken_after_roam()
    m = Motion()
    m.start(after, before, undo=True)
    assert m.capacity_pulse() == 0.0


def test_reduced_motion_skips_the_sparkle_and_the_pulse():
    before, after = taken_after_roam()
    m = Motion(reduced=True)
    m.start(before, after)
    assert m.sparkles() == [] and m.capacity_pulse() == 0.0
    assert m.capacity(5) == 5 and not m.running


def test_sparkle_and_pulse_stay_inside_the_documented_lengths():
    assert motion.LENGTHS["sparkle"] == motion.SPARKLE_FRAMES
    assert motion.LENGTHS["capacity"] == motion.CAPACITY_FRAMES
    assert motion.capacity_pulse(0) == 0.0
    assert motion.capacity_pulse(motion.CAPACITY_FRAMES) == 0.0


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
    assert "cell" in names and "conduit_off" in names and "conduit_live" not in names
    game = show(player, lit_state("lamp", "arc"))
    names = drawn_sprites(game)
    assert "conduit_live" in names and "conduit_off" not in names


def test_a_taken_cell_is_not_drawn_any_more(player):
    _, taken = taken_after_roam()
    names = drawn_sprites(show(player, taken))
    assert "cell" not in names


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
    assert ("conduit_live", False) in order
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
    for sprite in ("cell", "conduit_off", "conduit_live"):
        assert sprite in atlas
        assert manifest[sprite]["source"] == "derived"
        assert manifest[sprite]["status"] == "ok"


def test_recorded_failure_on_a_live_conduit_is_phrased_for_the_card():
    state = recording.enter(replace(lit_state("lamp", "arc"), player=HUB))
    state = replace(state, phase=Phase.RECORDING, player=CELL)
    result = recording.act(state, Move(1, 0))
    assert result.reason == lighting.LIVE
