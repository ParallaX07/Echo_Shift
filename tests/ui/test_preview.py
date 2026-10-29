"""Look-ahead previews, next-turn markers, in-world cues and the console modes."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from echo_shift.engine.loader import load
from echo_shift.engine.model import Phase, Position, initial_state
from echo_shift.engine.recording import act, enter, launch
from echo_shift.engine.turn import Accepted, InteractAtConsole, Move, Wait
from echo_shift.ui import controls, cues, preview
from echo_shift.ui.hud import model

ROOT = Path(__file__).resolve().parents[2]
MOVES = {
    "up": Move(0, -1),
    "right": Move(1, 0),
    "down": Move(0, 1),
    "left": Move(-1, 0),
    "wait": Wait(),
}


def committed(number):
    """Play a chamber's solution up to the saved recording."""
    chamber = load(ROOT / "levels" / f"chamber_{number:02}.json")
    steps = json.loads(
        (ROOT / "levels" / "solutions" / f"chamber_{number:02}.json").read_text()
    )["steps"]
    state = initial_state(chamber)
    for command in steps:
        if isinstance(command, dict):
            state = act(state, InteractAtConsole(frozenset(command["power"]))).state
        elif command == "enter":
            state = enter(state)
        else:
            state = act(state, MOVES[command]).state
        if state.phase is Phase.COMMITTED:
            return state
    raise AssertionError("solution never commits")


def example_60():
    chamber = load(ROOT / "levels" / "fixtures" / "example_60.json")
    state = act(
        initial_state(chamber), InteractAtConsole(frozenset({"lab-lights"}))
    ).state
    state = enter(state)
    state = act(state, Move(1, 0)).state
    state = act(state, Wait()).state
    state = enter(state)
    return act(state, InteractAtConsole(frozenset({"elevator-power"}))).state


def replaying(number):
    return launch(committed(number))


def facts(state):
    return (
        state.player,
        state.echo_position,
        state.pad_active,
        state.pad_occupied,
        state.pad_timers,
        state.gates_open,
        state.elevators_running,
    )


def frame_facts(frame):
    return (
        frame.player,
        frame.echo,
        frame.pads_active,
        frame.pads_occupied,
        frame.timers,
        frame.gates_open,
        frame.elevators_running,
    )


SOURCES = [
    pytest.param(lambda: committed(1), id="chamber-1"),
    pytest.param(lambda: committed(2), id="chamber-2"),
    pytest.param(lambda: committed(3), id="chamber-3"),
    pytest.param(example_60, id="example-60"),
]


@pytest.mark.parametrize("source", SOURCES)
def test_preview_for_turn_k_equals_the_live_state_after_k_waits(source):
    state = source()
    projection = preview.project(state)
    live = launch(state)
    assert frame_facts(projection.frames[0]) == facts(live)
    for turn in projection.turns:
        result = act(live, Wait())
        assert isinstance(result, Accepted)
        live = result.state
        assert frame_facts(projection.at(turn)) == facts(live), turn
    assert projection.turns[-1] == len(state.recording) + 2


@pytest.mark.parametrize("source", SOURCES)
def test_preview_never_mutates_the_live_state(source):
    for state in (source(), launch(source())):
        key, turns, snapshot = state.search_key(), state.turns, state
        preview.project(state)
        preview.markers(state)
        preview.echo_path(state)
        assert state is snapshot and state == snapshot
        assert state.search_key() == key and state.turns == turns


def test_preview_from_a_running_replay_starts_at_the_present():
    live = replaying(3)
    for _ in range(2):
        live = act(live, Wait()).state
    projection = preview.project(live)
    assert projection.base == 2 and projection.turns[0] == 3
    for turn in projection.turns:
        live = act(live, Wait()).state
        assert frame_facts(projection.at(turn)) == facts(live), turn


def test_expiry_matches_the_hold_rule():
    state = committed(3)  # four recorded commands
    count = len(state.recording)
    projection = preview.project(state)
    assert preview.last_present(state) == projection.last_present == count + 1
    assert projection.at(count + 1).echo is not None  # held through turn N+1
    assert projection.at(count + 2).echo is None  # gone at turn N+2
    assert preview.expiry_text(state) == f"ECHO LEAVES AFTER TURN {count + 1}"
    live = launch(state)
    for _ in range(count + 1):
        assert live.echo_position is not None
        live = act(live, Wait()).state
    live = act(live, Wait()).state
    assert live.echo_position is None
    assert preview.expiry_text(live) == "ECHO HAS LEFT"


def test_expiry_and_projection_need_a_saved_recording():
    chamber = load(ROOT / "levels" / "chamber_03.json")
    fresh = initial_state(chamber)
    assert preview.project(fresh) is None and preview.expiry_text(fresh) is None
    assert (
        preview.last_present(fresh) is None
        and preview.markers(fresh).closing == frozenset()
    )


def test_the_echo_path_and_next_command_follow_the_recording():
    state = committed(3)
    pad = state.chamber.pads[0].position
    path = tuple(Position(x, 5) for x in (6, 5, 4, 3)) + (pad, pad)
    assert preview.echo_path(state) == path
    live = launch(state)
    assert preview.next_command(live) == ("move", (-1, 0))
    live = act(live, Wait()).state
    assert preview.next_command(live) == ("move", (-1, 0))
    assert preview.echo_path(live) == path[1:]
    for _ in range(len(state.recording) - 1):
        live = act(live, Wait()).state
    assert preview.next_command(live) is None


def test_timed_pad_countdown_and_the_device_that_stops_next_turn():
    live = replaying(2)
    for _ in range(5):
        live = act(live, Move(1, 0)).state  # along the corridor
    live = act(live, Move(0, 1)).state  # onto the timed pad
    assert preview.markers(live).countdowns == (("pad-a", 3),)
    live = act(live, Move(0, -1)).state  # off it: the timer runs down
    assert preview.markers(live).countdowns == (("pad-a", 2),)
    live = act(live, Wait()).state
    markers = preview.markers(live)
    assert markers.countdowns == (("pad-a", 1),)
    assert markers.closing == {"lift"}  # the pad deactivates if the player waits
    live = act(live, Wait()).state
    assert preview.markers(live).countdowns == () and not live.elevators_running


def test_a_gate_closes_next_turn_when_its_echo_is_about_to_leave():
    state = committed(3)
    live = launch(state)
    for _ in range(len(state.recording)):
        live = act(live, Wait()).state
    assert "gate-a" in live.gates_open and preview.markers(live).closing == frozenset()
    live = act(live, Wait()).state  # the hold turn
    assert preview.markers(live).closing == {"gate-a", "lift"}
    live = act(live, Wait()).state
    assert "gate-a" not in live.gates_open


def test_past_slots_and_empty_slots_cannot_be_previewed():
    live = replaying(3)
    live = act(live, Wait()).state
    projection = preview.project(live)
    browser = preview.Browser()
    assert browser.slot_turn(live, 0, projection) is None  # already happened
    assert browser.slot_turn(live, 1, projection) == 2
    assert browser.slot_turn(live, 5, projection) is None  # empty slot
    assert model(live).timeline[0][1] is False  # only the next command is current
    for _ in range(len(live.recording) + 2):
        live = act(live, Wait()).state
    assert not any(current for _, current, _ in model(live).timeline)


def test_browser_steps_clamp_and_count_each_open_once():
    projection = preview.project(committed(3))
    browser = preview.Browser()
    assert browser.step(projection, 1) == 1
    assert browser.step(projection, -1) == 1  # clamps at the first turn
    assert browser.step(projection, 40) == projection.turns[-1]
    browser.release()
    assert browser.step(projection, -1) == projection.turns[-1]  # [ starts at the end
    assert browser.turn(projection) == projection.turns[-1]
    browser.hover = 2
    assert browser.turn(projection) == 2  # hovering wins over the chosen turn
    assert [browser.opened(browser.turn(projection)) for _ in range(3)] == [
        2,
        None,
        None,
    ]
    browser.hover = None
    assert browser.opened(browser.turn(projection)) == projection.turns[-1]
    assert browser.step(None, 1) is None


def committed_game(player, number=3):
    game = player.game
    game.open_level(number)
    player.press("F")
    player.to_console()
    keys = ("E", "SPACE", "RETURN", "RETURN", "LEFT")  # power, record here, one move
    for key in (*keys, "SPACE", "SPACE", "SPACE"):
        player.press(key)
    player.press("RETURN")
    assert game.state.phase is Phase.COMMITTED
    return game


def test_brackets_preview_turns_and_telemetry_counts_each_once(player):
    game = committed_game(player)
    player.press("RIGHTBRACKET")
    assert game.preview_turn() == 1
    for _ in range(3):
        game.update()
        game.draw()  # holding still opens nothing new
    assert game.attempt.previews == [1]
    player.press("RIGHTBRACKET")
    player.press("LEFTBRACKET")
    assert game.attempt.previews == [1, 2, 1]
    state, turns = game.state, game.state.turns
    assert game.preview_turn() == 1 and game.state is state and state.turns == turns
    player.press("RIGHT")  # any gameplay key is back to the live view
    assert game.preview_turn() is None
    player.press("RIGHTBRACKET")
    assert game.attempt.previews == [1, 2, 1, 1]


def test_brackets_are_refused_with_a_reason_before_a_recording_is_saved(player):
    game = player.game
    game.open_level(3)
    player.press("F")
    action = controls.find(game.play_actions(), "preview_next")
    assert not action.enabled and action.reason
    player.press("RIGHTBRACKET")
    assert game.preview_turn() is None and game.attempt.previews == []
    assert game.attempt.disabled_presses == {"preview_next": 1}


def test_hovering_a_slot_previews_it_and_leaving_the_strip_goes_live(player):
    game = committed_game(player)
    game.draw()
    rect = next(r for r, key in game.ui_hits if key == "timeline:2")
    player.fake.mouse_x, player.fake.mouse_y = rect[0] + 2, rect[1] + 2
    game.update()
    assert game.preview_turn() == 3 and game.attempt.previews == [3]
    game.update()
    assert game.attempt.previews == [3]
    player.fake.mouse_x = player.fake.mouse_y = -1
    game.update()
    assert game.preview_turn() is None
    player.fake.mouse_x, player.fake.mouse_y = rect[0] + 2, rect[1] + 2
    game.update()
    assert game.attempt.previews == [3, 3]
    empty = next(r for r, key in game.ui_hits if key == "timeline:5")
    player.fake.mouse_x, player.fake.mouse_y = empty[0] + 2, empty[1] + 2
    game.update()
    assert game.preview_turn() is None  # empty slots preview nothing


def test_clicking_a_slot_selects_it_as_a_preview(player):
    game = committed_game(player)
    game.draw()
    rect = next(r for r, key in game.ui_hits if key == "timeline:1")
    player.click(rect)
    assert game.preview_turn() == 2 and game.attempt.previews == [2]
    player.press("RIGHTBRACKET")  # the keys carry on from the clicked slot
    assert game.preview_turn() == 3


def test_drawing_a_preview_changes_nothing(player):
    game = committed_game(player)
    before = game.state
    player.press("RIGHTBRACKET")
    game.draw()
    assert game.state is before


def test_console_toggles_apply_at_once_and_undo_outside_replay(player):
    game = player.game
    game.open_level(2)
    player.press("F")
    player.to_console()
    player.press("E")
    first = game.state.chamber.circuits[0].id
    before = game.snapshot()
    player.press("SPACE")
    assert game.state.powered_circuits == {first} and game.state.turns == 0
    assert game.console and game.pending == {first}
    player.press("Z")
    assert game.snapshot() == before
    assert game.state.powered_circuits == frozenset()


def test_an_over_budget_toggle_is_refused_with_its_reason_and_counted_once(player):
    game = player.game
    game.open_level(2)
    player.press("F")
    player.to_console()
    player.press("E")
    for _ in game.state.chamber.circuits:
        player.press("SPACE")
        player.press("DOWN")
    assert game.state.powered_circuits == {"wing-lamp", "route-lights"}
    assert game.pending == {"wing-lamp", "route-lights", "lift-power"}
    assert game.attempt.unsafe_power_choices == 1
    assert "OVER BUDGET" in game.message
    player.press("RETURN")  # trying again changes nothing and is not counted twice
    assert game.state.powered_circuits == {"wing-lamp", "route-lights"}
    assert game.console
    assert game.attempt.unsafe_power_choices == 1


def test_apply_label_follows_the_phase():
    state = committed(3)
    free = controls.find(controls.available_actions(state, "game", "console"), "apply")
    assert free.label == "Done"
    staged = controls.find(
        controls.available_actions(launch(state), "game", "console"), "apply"
    )
    assert staged.label == "Apply (costs 1 turn)"


def test_replay_changes_are_staged_and_apply_costs_exactly_one_turn(player):
    game = committed_game(player)
    player.press("RETURN")  # launch
    assert game.state.phase is Phase.REPLAY
    for _ in range(2):
        player.press("LEFT")  # in replay the walk to the console costs turns
    player.press("E")
    assert game.console
    before, turns = game.state, game.state.turns
    player.press("SPACE")  # toggle lift-power off
    assert game.pending == frozenset() and game.state is before
    assert game.state.turns == turns and game.state.powered_circuits == {"lift-power"}
    apply = controls.find(game.actions(), "apply")
    assert apply.label == "Apply (costs 1 turn)"
    player.press("RETURN")
    assert game.state.turns == turns + 1
    assert game.state.powered_circuits == frozenset() and not game.console


def test_console_preview_lists_what_would_go_dark_and_change_power():
    chamber = load(ROOT / "levels" / "chamber_02.json")
    cell = frozenset({"cell-west"})  # the energy cell raises the limit to 50
    on = initial_state(chamber, frozenset({"route-lights", "lift-power"}), cell)
    path = set(next(zone.tiles for zone in chamber.zones if zone.id == "path"))
    shown = cues.console_preview(on, frozenset({"lift-power"}))
    assert shown.dark == path and not shown.lit
    assert shown.losing == frozenset() and shown.gaining == frozenset()
    off = cues.console_preview(on, frozenset())
    assert Position(14, 6) in off.dark and off.losing == {"lift"}
    fresh = initial_state(chamber, frozenset(), cell)
    gain = cues.console_preview(fresh, frozenset({"lift-power"}))
    assert gain.gaining == {"lift"} and gain.lit == {Position(14, 6)}
    assert not cues.console_preview(on, on.powered_circuits).changed


def test_unlit_neighbours_are_flagged_but_walls_and_closed_gates_are_not():
    chamber = load(ROOT / "levels" / "chamber_03.json")
    dark = initial_state(chamber)
    ahead = Position(dark.player.x + 1, dark.player.y)
    assert cues.unsafe_neighbours(dark) == (ahead,)
    assert (
        cues.unsafe_neighbours(initial_state(chamber, frozenset({"lift-power"}))) == ()
    )
    beside_gate = replace(dark, player=Position(12, 5))
    assert cues.unsafe_neighbours(beside_gate) == (Position(11, 5),)  # gate is shut
    assert not cues.warns_unsafe(dark)
    assert cues.warns_unsafe(replace(dark, phase=Phase.REPLAY))


def test_links_explain_why_a_powered_device_can_still_be_shut():
    state = launch(committed(3))
    for _ in range(len(state.recording)):
        state = act(state, Wait()).state  # the echo reaches pad A and holds it
    state = replace(state, player=Position(12, 5))
    links = {link.device.id: link for link in cues.focused_links(state, None)}
    assert set(links) == {"gate-a"}
    link = links["gate-a"]
    assert link.pad_label == "A" and link.pad_position == Position(3, 6)
    assert link.powered and link.pad_active and link.running
    unpowered = replace(state, powered_circuits=frozenset())
    shut = cues.focused_links(unpowered, Position(14, 5))
    assert {item.device.id for item in shut} == {"gate-a", "lift"}
    assert not any(item.powered for item in shut)


def pulses(player, still):
    """The outlines drawn on two different frames with the console preview on."""
    game = player.game
    game.open_level(2)
    player.press("F")
    player.to_console()
    player.press("E")
    chamber = game.state.chamber
    (console,) = chamber.consoles
    on = initial_state(chamber, frozenset({"lift-power"}), frozenset({"cell-west"}))
    game.state = replace(on, player=console)
    game.pending = frozenset()
    game.progress.settings.reduced_motion = still
    drawn = []
    player.fake.rectb = lambda *a: drawn.append(a)
    seen = []
    for frame in (0, 16):
        player.fake.frame_count = frame
        drawn.clear()
        game.draw()
        seen.append(list(drawn))
    return seen


def test_changing_devices_pulse_unless_motion_is_reduced(player):
    a, b = pulses(player, still=False)
    assert a != b


def test_reduced_motion_shows_a_static_outline_instead(player):
    a, b = pulses(player, still=True)
    assert a == b
    assert any(call[-1] == 8 for call in a)  # the outline is still drawn


# ---- badges over link lines, the countdown number, the preview legend ----------


def recording_draw(player, monkeypatch):
    """Log the order in which the cue drawers run."""
    from echo_shift.ui import cuedraw

    order = []
    for name in ("links", "badge", "countdown"):
        original = getattr(cuedraw, name)

        def wrapper(*args, _name=name, _original=original, **kwargs):
            order.append((_name, args))
            return _original(*args, **kwargs)

        monkeypatch.setattr(cuedraw, name, wrapper)
    return order


def beside_the_gate(player, monkeypatch):
    game = player.game
    game.open_level(3)
    game.modal = game.lesson = None
    live = launch(committed(3))
    for _ in range(len(live.recording)):
        live = act(live, Wait()).state  # the echo holds pad A
    game.state = replace(live, player=Position(12, 5))
    return game, recording_draw(player, monkeypatch)


def test_badges_are_drawn_after_every_link_line(player, monkeypatch):
    game, order = beside_the_gate(player, monkeypatch)
    game.draw()
    names = [name for name, _ in order]
    assert "links" in names and "badge" in names
    assert max(i for i, n in enumerate(names) if n == "links") < min(
        i for i, n in enumerate(names) if n == "badge"
    )


def test_badges_stay_above_the_link_lines_with_the_console_open_too(
    player, monkeypatch
):
    game, order = beside_the_gate(player, monkeypatch)
    (console,) = game.state.chamber.consoles
    game.state = replace(game.state, player=console)
    game.console, game.pending = True, frozenset()
    game.draw()
    assert [name for name, _ in order].count("badge") == 3  # pad A and its two devices


def test_the_countdown_number_is_larger_than_the_pad_letter(player, monkeypatch):
    game = player.game
    game.open_level(5)
    game.modal = game.lesson = None
    live = launch(committed(5))
    for _ in range(3):
        live = act(live, Wait()).state
    game.state = live
    order = recording_draw(player, monkeypatch)
    game.draw()
    countdown = next(args for name, args in order if name == "countdown")
    badge = next(args for name, args in order if name == "badge")
    _, _, _, value, scale, char, *_ = countdown
    assert value > 0
    assert scale > badge[4] and char > badge[5]  # bigger text than the letter badge


def legend_lines(player):
    """The drawn text lines made only of legend words."""
    words = {"POWER", "LIVE", "DARK", "OFF"}
    return [
        t.split()
        for t in player.drawn
        if t.split() and set(t.split()) <= words and t.startswith(" ")
    ]


def test_the_console_legend_names_only_the_frame_styles_in_the_preview(player):
    game = player.game
    game.open_level(4)
    game.modal = game.lesson = None
    chamber = game.state.chamber
    (console,) = chamber.consoles
    game.state = replace(
        initial_state(chamber, frozenset({"lab-lights"})), player=console
    )
    game.console, game.pending = True, frozenset({"lift-power"})
    player.drawn.clear()
    game.draw()
    assert legend_lines(player) == [["POWER", "LIVE", "DARK"]]
    game.pending = frozenset({"lab-lights"})  # nothing changes: no legend at all
    player.drawn.clear()
    game.draw()
    assert legend_lines(player) == []
    game.pending = frozenset()  # only the corridor goes dark
    player.drawn.clear()
    game.draw()
    assert legend_lines(player) == [["DARK"]]


def test_the_legend_swatches_sit_inside_the_drawer(player):
    game = player.game
    game.open_level(4)
    game.modal = game.lesson = None
    chamber = game.state.chamber
    (console,) = chamber.consoles
    game.state = replace(
        initial_state(chamber, frozenset({"lab-lights"})), player=console
    )
    game.console, game.pending = True, frozenset({"lift-power"})
    for _ in range(60):
        game.draw()  # the drawer has slid in
    x, y, width, height = game.layout.console_drawer()
    boxes = []
    player.fake.rectb = lambda *a: boxes.append(a)
    from echo_shift.ui import cuedraw

    swatches = []
    original = cuedraw.legend_swatch
    cuedraw.legend_swatch = lambda *a: (swatches.append(a), original(*a))
    try:
        game.draw()
    finally:
        cuedraw.legend_swatch = original
    assert [kind for kind, *_ in swatches] == ["power", "live", "dark"]
    for _, sx, sy, size in swatches:
        assert x <= sx and sx + size <= x + width
        assert y <= sy and sy + size <= y + height
