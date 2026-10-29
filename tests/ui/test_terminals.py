"""Log terminals: validated story props that open a free, undo-neutral card.

A terminal stands on plain floor that free roam can light: a hub tile or a tile of
a zone, anywhere in the chamber, so exploring a lit wing can be rewarded.
"""

import json
from dataclasses import replace

import pytest

from echo_shift.engine import loader
from echo_shift.engine.loader import LevelError, load
from echo_shift.engine.model import Phase, Position, TileType, initial_state
from echo_shift.engine.recording import enter, launch
from echo_shift.paths import resource_path
from echo_shift.ui import controls, guide, help, pointer, story
from echo_shift.ui.layout import Layout

CHAMBERS = range(1, 7)


def raw(number):
    return json.loads(resource_path("levels", f"chamber_{number:02}.json").read_text())


def chamber(number=1):
    return load(resource_path("levels", f"chamber_{number:02}.json"))


def terminals(number=1):
    return story.load_terminals(raw(number)["terminals"], chamber(number))


def item(x, y, lines=("A line.",)):
    return {"position": [x, y], "lines": list(lines)}


def near(number=1, index=0, dx=0, dy=0):
    """Terminals of a chamber, one of them, and a state with the player beside it."""
    found = terminals(number)
    at = found[index].position
    state = initial_state(chamber(number))
    return found, replace(state, player=Position(at.x + dx, at.y + dy))


# ---- loading and validation ------------------------------------------------------


@pytest.mark.parametrize("number", CHAMBERS)
def test_every_chamber_has_two_or_three_terminals_away_from_console_and_door(number):
    found = terminals(number)
    room = chamber(number)
    assert 2 <= len(found) <= 3
    (console,) = room.consoles
    lightable = {tile for zone in room.zones for tile in zone.tiles}
    for terminal in found:
        at = terminal.position
        assert at in room.hub or at in lightable
        assert abs(at.x - console.x) + abs(at.y - console.y) >= 3
        assert abs(at.x - room.start.x) + abs(at.y - room.start.y) >= 3
        assert 2 <= len(terminal.lines) <= 3


@pytest.mark.parametrize("number", CHAMBERS)
def test_terminal_tiles_are_plain_walkable_floor(number):
    room = chamber(number)
    plain = {TileType.HUB, TileType.FLOOR}
    assert all(room.tile_at(t.position) in plain for t in terminals(number))


@pytest.mark.parametrize("number", CHAMBERS)
def test_the_engine_ignores_terminals(number):
    data = raw(number)
    bare = {key: value for key, value in data.items() if key != "terminals"}
    assert loader.from_dict(data) == loader.from_dict(bare)


def test_no_terminals_is_fine():
    assert story.load_terminals(None, chamber()) == ()
    assert story.load_terminals([], chamber()) == ()


@pytest.mark.parametrize(
    "data",
    [
        "terminal",
        [{"position": [2, 4]}],
        [{"position": [2, 4], "lines": ["Hi."], "extra": 1}],
        [item(2, 4, ("",))],
        [item(2, 4, ("   ",))],
        [item(2, 4, ())],
        [item(2, 4, ("a", "b", "c", "d"))],
        [item(2, 4, ("x" * (story.MAX_LINE_CHARS + 1),))],
        [item(2, 4, (3,))],
        [{"position": [2, 4], "lines": "one line"}],
        [{"position": [2], "lines": ["Hi."]}],
        [{"position": [2.0, 4], "lines": ["Hi."]}],
        [{"position": [True, 3], "lines": ["Hi."]}],
        [item(0, 0)],  # a wall
        [item(12, 6)],  # a pad
        [item(12, 7)],  # the elevator
        [item(5, 5)],  # the console
        [item(8, 5)],  # the start
        [item(2, 4), item(2, 4)],  # the same tile twice
        [item(2, 4), item(3, 4)],  # two close together
    ],
)
def test_bad_terminals_are_rejected(data):
    with pytest.raises(LevelError):
        story.load_terminals(data, chamber(1))


def test_terminals_three_tiles_apart_are_accepted():
    found = story.load_terminals([item(1, 4), item(4, 4)], chamber(1))
    assert [t.position for t in found] == [Position(1, 4), Position(4, 4)]


def test_a_terminal_must_stand_where_free_roam_can_light_the_floor():
    data = raw(1)
    data["grid"][2][3] = "floor"  # open floor that no zone ever lights
    room = loader.from_dict(data)
    with pytest.raises(LevelError):
        story.load_terminals([item(3, 2)], room)


# ---- the action model ------------------------------------------------------------


def use(state, found, **kwargs):
    return controls.find(
        controls.available_actions(state, "game", None, terminals=found, **kwargs),
        "console",
    )


def test_read_log_is_offered_on_or_next_to_a_terminal():
    found, state = near()
    for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
        here = replace(state, player=Position(state.player.x + dx, state.player.y + dy))
        if here.chamber.tile_at(here.player) is TileType.WALL:
            continue
        action = use(here, found)
        assert (action.label, action.enabled, action.reason) == ("Read log", True, "")
        assert action.key == controls.BINDINGS["console"].cap
        assert action.short == ""


def test_the_use_key_keeps_its_power_label_and_reason_away_from_terminals():
    found, state = near()
    far = replace(state, player=Position(1, 6))
    action = use(far, found)
    assert not action.enabled
    assert action.label == "Power console"
    assert action.short == "Power"
    assert action.reason == "Stand on the hub console to change power"
    assert use(far, ()).reason == action.reason


def test_the_console_has_priority_when_standing_on_it():
    found, state = near()
    (console,) = state.chamber.consoles
    on_console = replace(state, player=console)
    assert use(on_console, found).label == "Power console"
    assert use(on_console, found).enabled
    # Even a terminal right beside it never takes the key from the console.
    beside = (story.Terminal(Position(console.x + 1, console.y), ("A line.",)),)
    assert story.in_reach(on_console, beside) is None
    assert use(on_console, beside).label == "Power console"


def test_reading_is_offered_in_every_phase():
    found, ready = near()
    base = initial_state(chamber())
    recording = enter(base)
    committed = enter(recording)
    replaying = launch(committed)
    for phase, state in {
        Phase.PREPARE: ready,
        Phase.RECORDING: recording,
        Phase.COMMITTED: committed,
        Phase.REPLAY: replaying,
    }.items():
        assert state.phase is phase
        # Recording and launching move the player to the start; stand on the terminal again.
        here = replace(state, player=ready.player)
        assert use(here, found).label == "Read log", phase


def test_reading_works_on_any_tile_next_to_a_terminal_not_only_in_the_hub():
    found, state = near(dx=1)  # a corridor tile beside the first terminal
    assert state.player not in state.chamber.hub
    assert story.in_reach(state, found) is found[0]
    assert use(state, found).enabled
    far = replace(state, player=Position(state.player.x + 2, state.player.y))
    assert story.in_reach(far, found) is None and not use(far, found).enabled


def test_only_the_play_scope_offers_the_log():
    found, state = near()
    for scope in ("console", "pause", "failure", "guide"):
        actions = controls.available_actions(state, "game", scope, terminals=found)
        assert all(a.label != "Read log" for a in actions), scope


def test_the_log_card_has_its_own_scope_with_labels():
    assert set(controls.SCOPES["log"]) >= {"confirm", "close"}
    _, state = near()
    actions = controls.available_actions(state, "game", "log")
    assert controls.find(actions, "confirm").label == "Next"
    assert controls.find(actions, "close").label == "Close"
    assert "KEY_E" in controls.key_names("close")


def test_the_guide_and_help_name_the_key_from_the_action_model():
    found, state = near()
    cap = controls.BINDINGS["console"].cap
    title, detail = help.room_info(state, found[0].position, terminals=found)
    assert title == "LOG TERMINAL"
    assert f"press {cap} to read" in detail
    topic = {k: d for k, _, d in help.topics(state, frozenset(), terminals=found)}
    at = found[0].position
    assert f"press {cap} to read" in topic[f"tile:{at.x},{at.y}"]
    plain = help.room_info(state, found[0].position)
    assert plain[0] != "LOG TERMINAL"
    notes = guide.objects(state, found)
    assert any(note.startswith("LOG TERMINAL") and cap in note for note in notes)
    assert not any(n.startswith("LOG TERMINAL") for n in guide.objects(state))
    assert any(
        line.startswith(f"{cap}:") and "log terminal" in line
        for line in controls.controls_lines(1)
    )


# ---- the mouse -------------------------------------------------------------------


def test_clicking_your_own_terminal_reads_and_an_adjacent_one_moves():
    found, state = near()
    at = found[0].position
    assert pointer.click_action(state, at, found) == pointer.READ_LOG  # underfoot
    for (dx, dy), action_id in (
        ((1, 0), "move_left"),
        ((-1, 0), "move_right"),
        ((0, 1), "move_up"),
        ((0, -1), "move_down"),
    ):
        beside = replace(state, player=Position(at.x + dx, at.y + dy))
        if beside.player in beside.chamber.hub:
            assert pointer.click_action(beside, at, found) == action_id
    here = replace(state, player=Position(at.x + 1, at.y))
    away = Position(at.x + 2, at.y)
    assert pointer.click_action(here, away, found) == "move_right"
    far = replace(state, player=Position(at.x + 3, at.y))
    assert pointer.click_action(far, at, found) is None  # not adjacent
    assert pointer.click_action(far, at) is None
    # Without the terminal, the own tile waits as ever.
    assert pointer.click_action(state, at) == "wait"


def test_clicking_the_console_tile_never_asks_for_a_log():
    found, state = near(dx=1)
    (console,) = state.chamber.consoles
    assert pointer.click_action(state, console, found) == pointer.POWER
    on_console = replace(state, player=console)
    assert pointer.click_action(on_console, console, found) == pointer.POWER


def test_hover_outlines_your_terminal_but_not_a_far_console():
    found, state = near()
    at = found[0].position
    actions = controls.available_actions(state, "game", None, terminals=found)
    assert pointer.hover_action(state, at, actions, found) == pointer.READ_LOG
    plain = controls.available_actions(state, "game", None)
    assert pointer.hover_action(state, at, plain) is None
    (console,) = state.chamber.consoles
    # The bar's key reads the log here, but the console tile is not clickable.
    assert controls.find(actions, "console").enabled
    assert pointer.hover_action(state, console, actions, found) is None
    on_console = replace(state, player=console)
    on_actions = controls.available_actions(on_console, "game", None, terminals=found)
    assert pointer.hover_action(on_console, console, on_actions, found) == "console"


# ---- the running game ------------------------------------------------------------


def recording(player, number=1):
    """Free play with a take started at the start tile."""
    game = player.game
    game.open_level(number)
    player.press("F")
    player.press("RETURN")
    assert game.state.phase is Phase.RECORDING
    return game


def start(player, number=1, index=0, dx=0, dy=0):
    game = player.game
    game.open_level(number)
    player.press("F")
    at = game.terminals[index].position
    game.state = replace(game.state, player=Position(at.x + dx, at.y + dy))
    game.pending = game.state.powered_circuits
    return game


def heard(player):
    names = {id(sound): name for name, sound in player.game.audio.sfx.items()}
    ids = [names[id(sound)] for channel, sound, _ in player.played if channel == 3]
    player.played.clear()
    return ids


def test_the_game_loads_each_chambers_terminals(player):
    for number in CHAMBERS:
        player.game.open_level(number)
        assert player.game.terminals == terminals(number)


def test_the_bar_offers_read_log_beside_a_terminal(player):
    game = start(player, dx=1)
    labels = {a.id: a.label for a in game.bar_actions()}
    assert labels["console"] == "Read log"
    game.state = replace(game.state, player=Position(1, 6))
    assert {a.id: a.label for a in game.bar_actions()}["console"] == "Power console"


def test_e_reads_without_a_turn_and_leaves_state_and_history_alone(player):
    game = start(player, dx=1)
    before, history, turns = game.snapshot(), len(game.history), game.state.turns
    player.press("E")
    assert game.modal == "log" and game.log is game.terminals[0]
    assert game.snapshot() == before
    assert game.state.turns == turns and len(game.history) == history
    player.press("E")  # E closes
    assert game.modal is None and game.snapshot() == before
    assert len(game.history) == history
    player.press("Z")  # nothing to undo: reading left no entry
    assert game.snapshot() == before


def test_the_card_advances_line_by_line_then_closes(player):
    game = start(player)
    lines = game.terminals[0].lines
    player.press("E")
    heard(player)
    for shown in range(2, len(lines) + 1):
        player.press("SPACE")
        assert (game.modal, game.log_page) == ("log", shown)
        assert heard(player) == ["dialogue"]
    player.press("RETURN")
    assert game.modal is None
    assert heard(player) == ["dialogue"]
    assert game.state.phase is Phase.PREPARE and len(game.history) == 0


def test_enter_and_a_click_advance_and_close(player):
    game = start(player)
    player.press("E")
    player.press("RETURN")
    assert game.log_page == 2
    while game.modal == "log":
        player.click_at(300, 300)
    assert game.log_page > len(game.log.lines) and len(game.history) == 0


@pytest.mark.parametrize("closer", ["ESCAPE", "E", "right"])
def test_escape_e_and_right_click_close_at_once(player, closer):
    game = start(player)
    before = game.snapshot()
    player.press("E")
    if closer == "right":
        player.click_at(300, 300, player.fake.MOUSE_BUTTON_RIGHT)
    else:
        player.press(closer)
    assert game.modal is None and not game.paused  # Esc closes, never pauses
    assert game.snapshot() == before and len(game.history) == 0


def test_keys_that_would_act_do_nothing_while_the_card_is_open(player):
    game = start(player)
    player.press("E")
    before = game.snapshot()
    for key in ("LEFT", "RIGHT", "UP", "DOWN", "Z", "R"):
        player.press(key)
    assert game.modal == "log" and game.snapshot() == before


def test_reading_works_while_recording_and_replaying(player):
    game = recording(player)
    game.state = replace(game.state, player=game.terminals[0].position)
    before, history = game.snapshot(), len(game.history)
    player.press("E")
    assert game.modal == "log"
    player.press("ESCAPE")
    assert game.modal is None
    assert game.snapshot() == before and len(game.history) == history
    assert game.state.recording == before.state.recording


def test_the_console_still_opens_on_the_console_and_refuses_elsewhere(player):
    game = start(player)
    (console,) = game.state.chamber.consoles
    game.state = replace(game.state, player=console)
    player.press("E")
    assert game.console and game.modal is None
    player.press("E")
    assert not game.console
    game.state = replace(game.state, player=Position(1, 6))
    player.press("E")
    assert not game.console and game.modal is None
    assert game.message == "STAND ON THE HUB CONSOLE TO CHANGE POWER"


def test_clicking_the_terminal_tile_next_to_the_player_moves_onto_it(player):
    game = start(player, dx=1)
    game.state = replace(
        initial_state(game.state.chamber, frozenset({"lift-power"})),
        player=game.state.player,
    )  # the side room has power, so the floor is lit
    at = game.terminals[0].position
    turns = game.state.turns
    player.click_tile(at.x, at.y)
    assert game.modal is None
    assert game.state.player == at and game.state.turns == turns


def test_clicking_underfoot_reads_instead_of_waiting_and_far_does_nothing(player):
    game = start(player)
    at = game.terminals[0].position
    before = game.snapshot()
    player.click_tile(at.x, at.y)
    assert game.modal == "log" and game.log is game.terminals[0]
    assert game.snapshot() == before and len(game.history) == 0
    player.press("ESCAPE")
    game.state = replace(game.state, player=Position(at.x + 4, at.y))
    before = game.snapshot()
    player.click_tile(at.x, at.y)
    assert game.modal is None and game.snapshot() == before


def test_clicking_underfoot_reads_while_recording_and_the_wait_button_waits(player):
    game = recording(player)
    at = game.terminals[0].position
    lit = frozenset({"lift-power"})  # waiting in the dark side room would fail the take
    game.state = replace(game.state, powered_circuits=lit)
    game.state = replace(game.state, player=at)
    turns = game.state.turns
    player.click_tile(at.x, at.y)
    assert game.modal == "log" and game.state.turns == turns
    player.press("ESCAPE")
    player.button("wait")
    assert game.modal is None and game.state.turns == turns + 1


def test_clicking_the_far_console_with_a_terminal_beside_you_is_refused(player):
    game = start(player, dx=1)
    (console,) = game.state.chamber.consoles
    before = game.snapshot()
    player.click_tile(console.x, console.y)
    assert game.modal is None and not game.console
    assert game.message == "STAND ON THE HUB CONSOLE TO CHANGE POWER"
    assert game.snapshot() == before
    game.state = replace(game.state, player=console)
    player.click_tile(console.x, console.y)
    assert game.console and game.modal is None


def test_the_bar_button_reads_the_log(player):
    game = start(player, dx=1)
    player.button("console")
    assert game.modal == "log"


def test_the_guide_opens_over_a_card_and_returns_to_it(player):
    game = start(player)
    player.press("E")
    player.press("T")
    assert game.modal == "guide"
    player.press("T")
    assert game.modal == "log" and game.log_page == 1


def test_terminals_are_drawn_by_sprite_id_on_the_floor(player):
    game = start(player, dx=1)
    drawn = []
    game.atlas = type("Atlas", (), {"draw": lambda self, *a: drawn.append(a[0])})()
    game.draw()
    # The camera follows the player, so only the terminals in view are drawn.
    assert 1 <= drawn.count("terminal") <= len(game.terminals)
    assert "floor_hub_inner" in drawn


# ---- text fits the canvas --------------------------------------------------------


@pytest.mark.parametrize("size", [(640, 480), (1280, 720), (1536, 864)])
def test_every_log_card_page_fits_the_canvas(player, size):
    game = player.game
    boxes = []
    original = game.text

    def checked(x, y, value, color=7, scale=None):
        scale = scale or game.layout.text_scale
        boxes.append((x, y, x + len(value) * 4 * scale, y + 7 * scale, value))
        original(x, y, value, color, scale)

    game.text = checked
    for number in CHAMBERS:
        game.open_level(number)
        player.press("F")
        game.layout = Layout.fit(*size)
        for index, terminal in enumerate(game.terminals):
            for page in range(1, len(terminal.lines) + 1):
                game.modal, game.log, game.log_page = "log", terminal, page
                boxes.clear()
                game.draw_log()
                assert any(b[4].startswith("LOG TERMINAL") for b in boxes)
                assert len(boxes) > page, (number, index, page)
                for left, top, right, bottom, value in boxes:
                    assert left >= 0 and top >= 0, value
                    assert right <= size[0] and bottom <= size[1], (size, value)
