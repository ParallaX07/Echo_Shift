"""Exercise checked lessons through real gameplay transitions and UI input."""

import copy
import json
from types import SimpleNamespace

import pytest

from echo_shift.engine.loader import LevelError, load
from echo_shift.engine.model import Phase, Position, initial_state
from echo_shift.paths import resource_path
from echo_shift.ui import app, progress, telemetry
from echo_shift.ui.help import room_info, topics
from echo_shift.ui.tutorial import Tutorial, load_steps


@pytest.fixture
def player(tmp_path, monkeypatch):
    real = app.pyxel
    keys = {name: getattr(real, name) for name in dir(real) if name.startswith("KEY_")}
    held, pressed = set(), set()
    drawn = []
    fake = SimpleNamespace(
        **keys,
        MOUSE_BUTTON_LEFT=real.MOUSE_BUTTON_LEFT,
        mouse_x=-1,
        mouse_y=-1,
        colors=[0] * 16,
        init=lambda *a, **k: None,
        btn=lambda k: k in held,
        btnp=lambda k, **kwargs: k in pressed,
        cls=lambda *a: None,
        rect=lambda *a: None,
        rectb=lambda *a: None,
        text=lambda *a: drawn.append(a[2]),
        pal=lambda *a: None,
    )
    monkeypatch.setattr(app, "pyxel", fake)
    monkeypatch.setattr(app, "Atlas", lambda: SimpleNamespace(draw=lambda *a: None))
    monkeypatch.setattr(
        app,
        "Display",
        lambda: SimpleNamespace(desktop_size=lambda: (1280, 720), window=lambda: None),
    )
    for module in (app, progress, telemetry):
        monkeypatch.setattr(module, "user_data_dir", lambda: tmp_path)
    game = app.Game()

    def press(name):
        key = keys["KEY_" + name]
        pressed.add(key)
        held.add(key)
        game.update()
        game.draw()
        pressed.clear()
        held.clear()
        game.update()  # release frame, including the lesson's repeat guard

    return SimpleNamespace(
        game=game,
        press=press,
        fake=fake,
        pressed=pressed,
        held=held,
        drawn=drawn,
        directory=tmp_path,
    )


def do_step(player):
    game = player.game
    step = game.lesson.current
    before = game.state
    player.press("RETURN")
    assert game.modal is None and game.state == before
    assert not game.lesson.explaining
    # Wrong gameplay input is inert even if the engine would normally accept it.
    player.press(
        "Q" if step.action == "toggle" else "UP" if step.action == "wait" else "SPACE"
    )
    assert game.state == before and game.lesson.current is step
    if step.action == "toggle":
        circuits = game.state.chamber.circuits
        while circuits[game.selection].id != step.target["id"]:
            player.press("DOWN")
        if len(circuits) > 1:
            player.press("DOWN")
            pending = game.pending
            player.press("SPACE")
            assert game.pending == pending and game.lesson.current is step
            player.press("UP")
    command = {
        "open_console": "E",
        "toggle": "SPACE",
        "apply": "RETURN",
        "enter": "RETURN",
        "launch": "Q",
        "right": "RIGHT",
        "wait": "SPACE",
        "retry": "R",
    }[step.action]
    player.press(command)
    assert game.lesson.current is not step
    if step.expected.get("outcome") == "rejected":
        assert game.state == before
        assert game.attempt.unsafe_power_choices == 1
    if step.action == "wait":
        assert len(game.state.recording) == len(before.recording) + 1
    return step


@pytest.mark.parametrize("number", [1, 2, 3])
def test_guided_playthrough_checks_every_step_and_unlocks(player, number):
    game = player.game
    game.open_level(number)
    assert game.modal == "lesson_choice"
    player.press("RETURN")
    visited = []
    while game.lesson.current:
        assert game.modal == "step"
        visited.append(do_step(player).id)
    assert game.state.phase is Phase.RESULT and game.modal == "result"
    assert visited == [s.id for s in game.lesson_steps]
    assert progress.load_unlocked(3) == min(number + 1, 3)
    record = json.loads(
        (player.directory / "playtest.jsonl").read_text().splitlines()[-1]
    )
    assert record["completed"] and record["mode"] == "guided"
    assert record["unsafe_power_choices"] == (1 if number == 2 else 0)
    assert record["resets"] == (1 if number == 1 else 0)


def test_help_hint_pause_hover_and_clear_preserve_or_restart_objective(player):
    game = player.game
    game.open_level(3)
    player.press("RETURN")
    before = game.state
    step = game.lesson.current
    player.press("H")
    assert game.modal == "hint"
    player.press("T")
    assert game.modal == "help"
    player.press("RIGHT")
    assert game.help_index == 1
    player.press("T")
    assert game.modal == "hint"
    player.press("RETURN")
    assert game.modal == "step" and game.lesson.current is step
    player.press("P")
    player.press("RETURN")
    assert game.paused and game.modal == "step"
    player.press("P")
    assert game.state == before and game.lesson.current is step
    # Inspect a dark pad without affecting state or progress.
    player.press("RETURN")
    cell, ox, oy = game.room_view
    player.fake.mouse_x, player.fake.mouse_y = (
        ox + 4 * cell + cell // 2,
        oy + 4 * cell + cell // 2,
    )
    before, index = game.state, game.lesson.index
    game.draw()
    title, detail = game.hovered_topic()
    assert "PAD A" in title and "Dark" in detail
    assert game.state == before and game.lesson.index == index
    player.press("C")
    assert game.state == initial_state(game.state.chamber)
    assert game.lesson.index == 0 and game.modal == "step"
    assert not game.console
    player.press("L")
    assert game.mode == "levels"


def test_held_movement_cannot_cross_explanation_or_acknowledgement(player):
    game = player.game
    game.open_level(3)
    player.press("RETURN")
    while game.lesson.current.id != "record-right":
        do_step(player)
    before, index = game.state, game.lesson.index
    player.pressed.update({player.fake.KEY_RETURN, player.fake.KEY_RIGHT})
    player.held.update({player.fake.KEY_RETURN, player.fake.KEY_RIGHT})
    game.update()
    assert game.modal is None and game.state == before
    player.pressed.clear()
    player.held.remove(player.fake.KEY_RETURN)
    # Simulate Pyxel's repeated btnp while Right remains held.
    player.pressed.add(player.fake.KEY_RIGHT)
    for _ in range(12):
        game.update()
    assert game.state == before and game.lesson.index == index
    player.pressed.clear()
    player.held.clear()
    game.update()
    player.press("RIGHT")
    assert game.lesson.current.id == "wait-one"
    assert game.state.player == Position(4, 4)
    player.press("RIGHT")
    assert game.lesson.current.id == "wait-one" and len(game.state.recording) == 1


def test_retry_rewinds_to_replay_objective_with_same_take(player):
    game = player.game
    game.open_level(3)
    player.press("RETURN")
    while game.lesson.current.id != "replay-gate":
        do_step(player)
    recording, powered = game.state.recording, game.state.powered_circuits
    player.press("RETURN")
    player.press("R")
    assert game.lesson.current.id == "replay-pad" and game.modal == "step"
    assert game.state.player == game.state.chamber.start
    assert game.state.echo_index == 0
    assert game.state.recording == recording and game.state.powered_circuits == powered
    while game.lesson.current:
        do_step(player)
    assert game.modal == "result"


def test_controller_does_not_advance_on_key_without_expected_result():
    chamber = load(resource_path("levels", "chamber_01.json"))
    data = json.loads(resource_path("levels", "chamber_01.json").read_text())
    tutorial = Tutorial(load_steps(data["tutorial_steps"], chamber))
    state = initial_state(chamber)
    assert not tutorial.observe("open_console", state, frozenset(), True)
    tutorial.explaining = False
    assert not tutorial.observe("open_console", state, frozenset(), False)
    assert tutorial.index == 0
    assert tutorial.observe("open_console", state, frozenset(), True)


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s.pop("explanation"),
        lambda s: s.update(action="teleport"),
        lambda s: s.update(expected={"powered": ["missing"]}),
        lambda s: s.update(expected={"active_pad": "missing"}),
        lambda s: s.update(expected={"open_gate": "missing"}),
        lambda s: s.update(expected={"player": [99, 4]}),
        lambda s: s.update(expected={"recorded": 7}),
        lambda s: s.update(target={"kind": "timeline", "index": 6}),
        lambda s: s.update(target={"kind": "circuit", "id": "missing"}),
        lambda s: s.update(expected={"console": "yes"}),
        lambda s: s.update(expected={"outcome": "failed"}),
        lambda s: s.update(expected={"phase": "flying"}),
        lambda s: s.update(expected={"surprise": 1}),
    ],
)
def test_malformed_lesson_content_is_rejected(change):
    chamber = load(resource_path("levels", "chamber_01.json"))
    data = json.loads(resource_path("levels", "chamber_01.json").read_text())[
        "tutorial_steps"
    ]
    change(data[0])
    with pytest.raises(LevelError):
        load_steps(data, chamber)
    assert load_steps(None, chamber) == ()


def test_duplicate_step_ids_are_rejected():
    chamber = load(resource_path("levels", "chamber_01.json"))
    steps = json.loads(resource_path("levels", "chamber_01.json").read_text())[
        "tutorial_steps"
    ]
    with pytest.raises(LevelError):
        load_steps([steps[0], copy.deepcopy(steps[0])], chamber)


def test_contextual_explanations_reflect_live_state_and_keyboard_topics(player):
    game = player.game
    game.open_level(2)
    player.press("F")
    player.press("E")
    player.press("SPACE")
    entries = {
        key: (title, detail)
        for key, title, detail in topics(game.state, game.pending, game.console)
    }
    assert "Pending choice: 20/60" in entries["power"][1]
    assert "Applied: OFF. Pending: ON" in entries["circuit:path-lights"][1]
    title, detail = room_info(game.state, Position(4, 4))
    assert "TIMED" in title and "Timer: 0/3" in detail and "Occupied: no" in detail
    assert (
        "circuit:lift-power" in entries
        and "tile:6,4" in entries
        and "timeline:5" in entries
    )
    before = game.state
    player.press("T")
    for _ in entries:
        player.press("RIGHT")
    player.press("ESCAPE")
    assert game.console and game.modal is None and game.state == before


@pytest.mark.parametrize("number", [1, 2, 3])
def test_free_play_uses_existing_solution_and_records_mode(player, number):
    game = player.game
    game.open_level(number)
    player.press("F")
    assert game.lesson is None and game.modal is None
    steps = json.loads(
        resource_path("levels", "solutions", f"chamber_{number:02}.json").read_text()
    )["steps"]
    for command in steps:
        if isinstance(command, dict):
            player.press("E")
            for index, circuit in enumerate(game.state.chamber.circuits):
                while game.selection != index:
                    player.press("DOWN")
                if (circuit.id in game.pending) != (circuit.id in command["power"]):
                    player.press("SPACE")
            player.press("RETURN")
        else:
            player.press(
                {"enter": "RETURN", "launch": "Q", "right": "RIGHT", "wait": "SPACE"}[
                    command
                ]
            )
    assert game.modal == "result"
    record = json.loads(
        (player.directory / "playtest.jsonl").read_text().splitlines()[-1]
    )
    assert record["completed"] and record["mode"] == "free"


def test_mode_choices_are_clickable_and_help_from_choice_returns(player):
    game = player.game
    for choice in (0, 1):
        game.open_level(1)
        player.press("T")
        player.press("ESCAPE")
        assert game.modal == "lesson_choice"
        game.draw()
        x, y, width, height = game.choice_hits[choice]
        player.fake.mouse_x, player.fake.mouse_y = x + width // 2, y + height // 2
        player.pressed.add(player.fake.MOUSE_BUTTON_LEFT)
        game.update()
        player.pressed.clear()
        assert (game.lesson is not None) == (choice == 0)
        assert game.state.turns == 0


@pytest.mark.parametrize(
    "invalid",
    [
        {"expected": {"phase": []}},
        {"expected": {"outcome": {}}},
        {"expected": {"pending": [[]]}},
        {"target": {"kind": []}},
        {"target": {"kind": "tile", "position": [True, 4]}},
        {"expected": {}},
        {"target": None},
        {"expected": None},
    ],
)
def test_malformed_field_types_raise_level_error(invalid):
    chamber = load(resource_path("levels", "chamber_01.json"))
    step = json.loads(resource_path("levels", "chamber_01.json").read_text())[
        "tutorial_steps"
    ][0]
    step.update(invalid)
    with pytest.raises(LevelError):
        load_steps([step], chamber)
