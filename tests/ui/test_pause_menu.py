"""Pause menu actions, Esc handling and the hidden launch alias."""

from echo_shift.engine.model import Phase
from echo_shift.ui import app, controls


def start(player, number=3):
    player.game.open_level(number)
    player.press("F")
    return player.game


def test_escape_pauses_instead_of_quitting(player):
    game = start(player)
    player.press("ESCAPE")
    assert game.paused
    player.press("ESCAPE")
    assert not game.paused
    player.press("P")
    assert game.paused
    player.press("P")
    assert not game.paused


def test_pyxel_is_initialised_without_an_escape_quit_key(tmp_path, monkeypatch):
    calls = []
    real = app.pyxel
    from types import SimpleNamespace

    keys = {n: getattr(real, n) for n in dir(real) if n.startswith("KEY_")}
    fake = SimpleNamespace(
        **keys,
        colors=[0] * 16,
        init=lambda *a, **k: calls.append(k),
    )
    monkeypatch.setattr(app, "pyxel", fake)
    monkeypatch.setattr(app, "Atlas", lambda: None)
    monkeypatch.setattr(app, "user_data_dir", lambda: tmp_path)
    monkeypatch.setattr(app.progress, "user_data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        app,
        "Display",
        lambda: SimpleNamespace(desktop_size=lambda: (1280, 720), window=lambda: None),
    )
    app.Game()
    assert calls[0]["quit_key"] == keys["KEY_NONE"] != keys["KEY_ESCAPE"]


def test_l_opens_chamber_select_only_inside_the_pause_menu(player):
    game = start(player)
    player.press("L")
    assert game.mode == "game"
    player.press("P")
    player.press("L")
    assert game.mode == "levels"


def test_escape_closes_the_console_before_it_pauses(player):
    game = start(player)
    player.to_console()
    player.press("E")
    assert game.console
    player.press("ESCAPE")
    assert not game.console and not game.paused
    player.press("ESCAPE")
    assert game.paused


def test_pause_menu_lists_actions_with_reasons_for_disabled_ones(player):
    game = start(player)
    player.press("P")
    player.drawn.clear()
    game.draw()
    text = " | ".join(player.drawn)
    for item in app.PAUSE_ITEMS:
        action = controls.find(game.actions(), item)
        assert action.label in text
        if not action.enabled:
            assert action.reason in text
    assert not controls.find(game.actions(), "undo").enabled


def test_pause_menu_navigates_and_confirms_with_enter(player):
    game = start(player)
    player.press("RETURN")  # record
    player.press("P")
    assert game.pause_index == 0
    player.press("DOWN")
    assert game.pause_index == 1
    player.press("UP")
    player.press("UP")
    assert game.pause_index == len(app.PAUSE_ITEMS) - 1
    for _ in range(app.PAUSE_ITEMS.index("quit_title") - 3):
        player.press("UP")
    assert app.PAUSE_ITEMS[game.pause_index] == "restart"
    player.press("RETURN")
    assert not game.paused and game.state.phase is Phase.PREPARE
    player.press("Z")
    assert game.state.phase is Phase.RECORDING


def test_pause_menu_undo_retry_and_rerecord(player):
    game = start(player)
    player.press("RETURN")
    player.press("SPACE")
    recorded = game.state
    assert recorded.recording
    player.press("P")
    game.pause_index = app.PAUSE_ITEMS.index("rerecord")
    player.press("RETURN")
    assert not game.paused
    assert game.state.phase is Phase.PREPARE and not game.state.recording
    player.press("P")
    player.press("Z")
    assert game.state == recorded and not game.paused


def test_disabled_pause_item_shows_its_reason_and_counts(player):
    game = start(player)
    player.press("P")
    player.press("R")
    assert game.paused
    assert game.attempt.disabled_presses == {"retry": 1}
    assert game.message == controls.find(game.actions(), "retry").reason.upper()


def test_quit_to_title_from_the_pause_menu(player):
    game = start(player)
    player.press("P")
    game.pause_index = app.PAUSE_ITEMS.index("quit_title")
    player.press("RETURN")
    assert game.mode == "title" and not game.paused


def test_echo_key_enter_f_and_hidden_q(player):
    game = start(player)
    player.to_console()
    for key in ("E", "SPACE", "RETURN", "RETURN", "RETURN"):  # power, record, save
        player.press(key)
    assert game.state.phase is Phase.COMMITTED
    action = controls.find(game.actions(), "echo")
    assert (action.key, action.label) == ("Enter", "Launch echo")
    player.press("F")
    assert game.state.phase is Phase.REPLAY
    assert game.attempt.disabled_presses == {}


def test_q_launches_but_never_starts_or_saves_a_recording(player):
    game = start(player)
    player.press("Q")
    assert game.state.phase is Phase.PREPARE
    assert game.attempt.disabled_presses == {"echo": 1}
    player.press("RETURN")
    player.press("Q")
    assert game.state.phase is Phase.RECORDING
    for key in ("RETURN", "Q"):
        player.press(key)
    assert game.state.phase is Phase.REPLAY


def test_echo_key_is_refused_with_its_reason_while_the_echo_runs(player):
    game = start(player)
    for key in ("RETURN", "RETURN", "RETURN"):
        player.press(key)
    assert game.state.phase is Phase.REPLAY
    before = game.state
    player.press("RETURN")
    assert game.state == before
    reason = controls.find(game.actions(), "echo").reason
    assert game.message == reason.upper()
    assert game.attempt.disabled_presses == {"echo": 1}


def test_guided_undo_rewinds_the_lesson(player):
    game = player.game
    game.open_level(3)
    player.press("RETURN")  # start the lesson
    player.press("RETURN")  # ready to try
    assert game.lesson.index == 0
    for _ in range(4):
        player.press("LEFT")  # walk to the console
    assert game.lesson.index == 1 and not game.console
    player.press("E")  # opens the console and advances the lesson
    assert game.console and game.lesson.index == 2
    player.press("RETURN")  # ready to try the next step
    assert game.modal is None
    player.press("Z")
    assert game.lesson.index == 1 and not game.console
    assert game.lesson.current.action == "open_console"
    player.press("E")
    assert game.lesson.index == 2 and game.console
