"""Progressive disclosure, the guide, the pause menu's settings and lesson wording."""

import json
import re

import pytest

from echo_shift.engine.loader import load
from echo_shift.paths import resource_path
from echo_shift.ui import app, controls, guide, progress
from echo_shift.ui.help import topics
from echo_shift.ui.tutorial import load_hints, load_steps

NEW_BUTTONS = {"console", "echo", "retry", "rerecord"}
SOLUTION_ACTIONS = {
    "enter": "echo",
    "launch": "echo",
    "right": "move_right",
    "left": "move_left",
    "up": "move_up",
    "down": "move_down",
    "wait": "wait",
}


def buttons(player, level):
    player.game.open_level(level)
    player.game.modal = None
    player.game.draw()
    return {
        key.removeprefix("action:")
        for _, key in player.game.ui_hits
        if key.startswith("action:")
    }


def free_game(player, level=3):
    player.game.open_level(level)
    player.press("F")
    return player.game


# ---- progressive disclosure ------------------------------------------------------


def test_chambers_show_actions_as_they_are_introduced():
    shown = {level: controls.shown_actions(level) for level in range(1, 7)}
    always = {"restart", "pause", "guide", "hint", "mute", "fullscreen"}
    basics = {"move_up", "move_down", "move_left", "move_right", "wait", "undo"}
    assert shown[1] == always | basics | {"console", "echo"}
    assert shown[2] == shown[1]
    assert shown[3] == set(controls.SCOPES["play"])
    assert shown[3] == shown[4] == shown[5] == shown[6]
    assert controls.introduced(1) == ("console", "echo")
    assert controls.introduced(2) == ()
    assert set(controls.introduced(3)) >= {"retry", "rerecord"}


@pytest.mark.parametrize("level", [1, 2, 3, 4, 5, 6])
def test_bar_buttons_follow_the_chamber(player, level):
    present = buttons(player, level) & NEW_BUTTONS
    expected = NEW_BUTTONS if level >= 3 else {"console", "echo"}
    assert present == expected
    assert {"wait", "undo", "restart", "guide", "hint", "pause"} <= buttons(
        player, level
    )


@pytest.mark.parametrize("level", [1, 2, 3, 4, 5, 6])
def test_disclosure_never_hides_what_the_chamber_needs(level):
    shown = controls.shown_actions(level)
    path = resource_path("levels", "solutions", f"chamber_{level:02}.json")
    for token in json.loads(path.read_text())["steps"]:
        needed = "console" if isinstance(token, dict) else SOLUTION_ACTIONS[token]
        assert needed in shown, (level, token)
    data = json.loads(resource_path("levels", f"chamber_{level:02}.json").read_text())
    chamber = load(resource_path("levels", f"chamber_{level:02}.json"))
    ids = {
        "open_console": "console",
        "enter": "echo",
        "launch": "echo",
        "right": "move_right",
        "up": "move_up",
        "down": "move_down",
        "wait": "wait",
        "retry": "retry",
    }
    for step in load_steps(data["tutorial_steps"], chamber):
        if step.action in ids:
            assert ids[step.action] in shown, (level, step.id)


def test_hidden_actions_keep_working_by_key(player):
    game = free_game(player, 1)
    assert "retry" not in buttons(player, 1)
    game.open_level(1)
    player.press("F")
    player.to_console()
    for key in ("E", "SPACE", "RETURN", *["RIGHT"] * 3):
        player.press(key)
    for key in ("RETURN", "RETURN", "RETURN", "RIGHT"):
        player.press(key)
    moved = game.state
    player.press("R")  # retry is not on chamber 1's bar, but its key works
    assert game.state != moved and game.state.player == game.state.chamber.start


def test_new_buttons_blink_once_and_stay_lit_with_reduced_motion(player):
    game = player.game
    game.open_level(3)
    assert game.intro_frames > 0
    key = "action:retry"
    states = []
    for _ in range(40):
        game.modal = None
        game.update()
        states.append(game.introducing(key))
    assert True in states and False in states  # blinks
    assert not game.introducing("action:undo")
    game.intro_frames = 0
    assert not game.introducing(key)
    game.open_level(3)
    assert game.intro_frames == 0  # only the first time
    game.open_level(2)
    assert game.intro_frames == 0  # nothing new in chamber 2
    game.open_level(3)
    game.progress.settings.reduced_motion = True
    game.intro_frames = 60
    lit = []
    for _ in range(10):
        lit.append(game.introducing(key))
        game.update()
    assert all(lit)  # static when motion is reduced


def test_new_button_highlight_is_drawn_on_the_bar(player):
    game = player.game
    outlines = []
    player.fake.rectb = lambda *a: outlines.append(a)
    game.open_level(1)
    game.modal = None
    game.progress.settings.reduced_motion = True
    game.draw()
    rects = {key: rect for rect, key in game.ui_hits if key.startswith("action:")}
    x, y, w, h = rects["action:echo"]
    assert (x + 1, y + 1, w - 2, h - 2, 9) in outlines
    assert (rects["action:undo"][0] + 1, rects["action:undo"][1] + 1) not in [
        (o[0], o[1]) for o in outlines if o[4] == 9
    ]


# ---- the guide ---------------------------------------------------------------------


def text_of(player):
    player.drawn.clear()
    player.game.draw()
    return " | ".join(player.drawn)


def test_controls_page_is_generated_from_the_action_model(player):
    for level, rerecord in ((1, False), (3, True)):
        game = free_game(player, level)
        player.press("T")
        game.guide_page = guide.PAGE_IDS.index("controls")
        lines = guide.page_lines("controls", game.state, level=level)
        assert lines == [
            controls.resolve(line) for line in controls.controls_lines(level)
        ]
        shown = text_of(player)
        for line in lines:
            assert line.split(": ")[0] in shown
        assert ("Throw away the recording" in " ".join(lines)) is rerecord
        assert ("Run the echo again" in " ".join(lines)) is rerecord
        assert "Q" not in [line.split(":")[0] for line in lines]
        player.press("T")


def test_guide_has_the_seven_pages_in_order():
    assert guide.PAGE_IDS == (
        "goal",
        "controls",
        "objects",
        "echo",
        "power",
        "hints",
        "rules",
    )


def test_guide_pages_navigate_by_keys_and_mouse(player):
    game = free_game(player)
    player.press("T")
    assert game.modal == "guide" and game.guide_page == 0
    player.press("RIGHT")
    player.press("D")
    player.press("DOWN")
    assert game.guide_page == 3
    player.press("LEFT")
    player.press("A")
    player.press("UP")
    assert game.guide_page == 0
    player.press("UP")
    assert game.guide_page == 6  # wraps
    player.click_row("row:guide:next")
    assert game.guide_page == 0
    player.click_row("row:guide:next")
    player.click_row("row:guide:prev")
    player.click_row("row:guide:prev")
    assert game.guide_page == 6


@pytest.mark.parametrize("closer", ["ESCAPE", "E", "T", "mouse"])
def test_guide_closes_without_changing_the_game(player, closer):
    game = free_game(player)
    before = game.state
    player.press("T")
    if closer == "mouse":
        player.click_at(20, 20, player.fake.MOUSE_BUTTON_RIGHT)
    else:
        player.press(closer)
    assert game.modal is None and game.state == before and not game.paused


def test_every_page_draws_inside_the_window(player):
    game = free_game(player, 3)
    player.press("T")
    for index, page in enumerate(guide.PAGE_IDS):
        game.guide_page = index
        shown = text_of(player)
        assert guide.title(page) in shown
    assert "{" not in shown


def test_hints_page_lists_revealed_hints_and_counts_what_remains(player):
    game = free_game(player)
    total = len(game.hints)
    assert total >= 2
    assert guide.hints((), total)[0].startswith(f"{total} more hints left")
    player.press("H")
    assert game.modal == "guide"
    assert guide.PAGE_IDS[game.guide_page] == "hints"
    assert game.hint_index == 1 and game.attempt.hints == 1
    lines = guide.page_lines(
        "hints", game.state, level=3, revealed=game.hints[:1], total_hints=total
    )
    assert lines[0].startswith("1. ") and lines[-1].startswith(f"{total - 1} more")
    assert "H" in lines[-1] and "{" not in " ".join(lines)
    player.press("H")  # inside the guide it reveals the next hint
    assert game.hint_index == 2 and game.attempt.hints == 2
    for _ in range(total):
        player.press("H")
    assert game.hint_index == total and game.attempt.hints == total
    assert game.modal == "guide"
    assert guide.hints(game.hints, total)[-1] == "No more hints in this chamber."
    shown = text_of(player)
    assert "No more hints" in shown and "1." in shown


def test_h_outside_the_guide_opens_the_hints_page_from_any_page(player):
    game = free_game(player)
    player.press("T")
    game.guide_page = 4
    player.press("ESCAPE")
    player.press("H")
    assert guide.PAGE_IDS[game.guide_page] == "hints" and game.hint_index == 1
    player.press("T")
    assert game.modal is None
    player.press("T")
    assert guide.PAGE_IDS[game.guide_page] == "goal"
    game.guide_page = 4
    player.press("H")  # from another page it jumps to the hints
    assert guide.PAGE_IDS[game.guide_page] == "hints"


def test_precise_rules_page_states_the_exact_timing_in_plain_words(player):
    game = free_game(player)
    text = " ".join(guide.page_lines("rules", game.state, level=3)).lower()
    for phrase in (
        "one extra turn",
        "costs a turn and takes effect that same turn",
        "rejected inputs cost nothing",
        "uses it up",
        "recomputed after the echo leaves, after a power change",
        "the echo leaves if its time is up",
    ):
        assert phrase in text
    assert not re.search(r"\bR\d+\b", text.upper())


def test_objects_page_explains_what_the_chamber_contains(player):
    game = free_game(player)
    text = " ".join(guide.page_lines("objects", game.state, level=3))
    for word in ("YOU", "ECHO", "HUB", "PAD A", "GATE", "ELEVATOR"):
        assert word in text


def test_guide_and_topic_text_has_no_hard_coded_keys_or_turn_jargon(player):
    game = free_game(player)
    for name in ("GOAL", "ECHO", "POWER", "RULES"):
        for line in getattr(guide, name):
            assert not KEYS.search(line), line
            controls.check_text(line)
    everything = [
        line
        for page in guide.PAGE_IDS
        for line in guide.page_lines(page, game.state, level=3)
    ] + [detail for _, _, detail in topics(game.state, game.pending)]
    assert not any(JARGON.search(line) for line in everything)


# ---- the pause menu and settings ---------------------------------------------------


def test_pause_menu_lists_every_listed_action_with_labels_from_the_action_model(player):
    game = free_game(player)
    assert app.PAUSE_ITEMS == (
        "pause",
        "undo",
        "retry",
        "restart",
        "rerecord",
        "levels",
        "settings",
        "controls",
        "quit_title",
    )
    player.press("P")
    shown = text_of(player)
    for item in app.PAUSE_ITEMS:
        assert controls.BINDINGS[item].label in shown or item == "pause"
    assert controls.find(game.actions(), "pause").label == "Resume"
    assert controls.find(game.actions(), "settings").enabled


def open_settings(player):
    game = free_game(player)
    player.press("P")
    game.pause_index = app.PAUSE_ITEMS.index("settings")
    player.press("RETURN")
    assert game.paused and game.settings_open
    return game


def test_settings_change_with_left_right_and_persist(player):
    game = open_settings(player)
    settings = game.progress.settings
    assert settings.music_volume == progress.MAX_VOLUME
    player.press("LEFT")
    player.press("A")
    assert settings.music_volume == progress.MAX_VOLUME - 2
    for _ in range(10):
        player.press("LEFT")
    assert settings.music_volume == 0  # clamped
    player.press("RIGHT")
    assert progress.load(3).settings.music_volume == 1
    player.press("DOWN")
    player.press("LEFT")
    assert settings.sfx_volume == progress.MAX_VOLUME - 1
    player.press("DOWN")
    player.press("RIGHT")
    assert settings.mute and progress.load(3).settings.mute
    player.press("DOWN")
    player.press("RETURN")
    assert settings.reduced_motion and progress.load(3).settings.reduced_motion
    saved = progress.load(3).settings
    assert (saved.music_volume, saved.sfx_volume) == (1, progress.MAX_VOLUME - 1)


def test_settings_can_be_changed_by_clicking_and_fullscreen_row_toggles(player):
    game = open_settings(player)
    settings = game.progress.settings
    game.draw()
    x, y, w, h = next(r for r, k in game.ui_hits if k == "row:setting:music_volume")
    player.click_at(x + 4, y + h // 2)  # left half lowers
    assert settings.music_volume == progress.MAX_VOLUME - 1
    player.click_at(x + w - 4, y + h // 2)  # right half raises
    assert settings.music_volume == progress.MAX_VOLUME
    player.click_row("row:setting:reduced_motion")
    assert settings.reduced_motion
    calls = []
    game.toggle_fullscreen = lambda: calls.append("fullscreen")
    player.click_row("row:setting:fullscreen")
    assert calls == ["fullscreen"]
    assert progress.load(3).settings.reduced_motion


def test_settings_back_returns_to_the_pause_menu_and_labels_come_from_controls(player):
    game = open_settings(player)
    shown = text_of(player)
    for item in app.SETTINGS_ITEMS:
        assert controls.find(game.actions(), item).label in shown
    player.press("ESCAPE")
    assert game.paused and not game.settings_open
    game.pause_index = app.PAUSE_ITEMS.index("settings")
    player.press("RETURN")
    game.settings_index = len(app.SETTINGS_ITEMS) - 1
    player.press("RETURN")
    assert game.paused and not game.settings_open
    game.pause_index = app.PAUSE_ITEMS.index("settings")
    player.click_row("row:pause:settings")
    assert game.settings_open
    player.click_row("row:setting:close")
    assert game.paused and not game.settings_open


def test_settings_survive_a_new_session(player):
    game = open_settings(player)
    player.press("LEFT")
    saved = progress.load(3)
    assert saved.settings.music_volume == progress.MAX_VOLUME - 1
    assert game.progress.settings == saved.settings


def test_pause_controls_item_opens_the_guide_on_the_controls_page(player):
    game = free_game(player)
    player.press("P")
    player.click_row("row:pause:controls")
    assert not game.paused and game.modal == "guide"
    assert guide.PAGE_IDS[game.guide_page] == "controls"
    player.press("ESCAPE")
    assert game.modal is None


# ---- level text ----------------------------------------------------------------------

KEYS = re.compile(
    r"\b(Enter|Return|Space|Esc|Escape|Backspace|WASD|F11|Shift|Ctrl|Tab|"
    r"Up|Down|Left|Right|arrows?)\b|(?<![A-Za-z-])[WSDERCZTHMPQF](?![A-Za-z-])"
)
JARGON = re.compile(r"\bN ?\+ ?\d|\bturn N\b|\bR\d{1,2}\b", re.IGNORECASE)


def level_texts(number):
    path = resource_path("levels", f"chamber_{number:02}.json")
    data = json.loads(path.read_text())
    texts = [data["lesson_summary"], *data["hints"]]
    for step in data["tutorial_steps"]:
        texts += [step["objective"], step.get("title", ""), step.get("explanation", "")]
    return [text for text in texts if text]


@pytest.mark.parametrize("number", [1, 2, 3, 4, 5, 6])
def test_level_text_names_keys_only_through_placeholders(number):
    texts = level_texts(number)
    assert len(texts) > 8
    for text in texts:
        assert not KEYS.search(text), text
        assert not JARGON.search(text), text
        controls.check_text(text)
        resolved = controls.resolve(text)
        assert "{" not in resolved and "}" not in resolved
        assert not JARGON.search(resolved), resolved
        assert "toggle does not apply" not in text.lower()
        assert "twice" not in text.lower() or "{key:echo}" in text


@pytest.mark.parametrize("number", [1, 2, 3, 4, 5, 6])
def test_hints_and_summary_load_through_the_validators(number):
    path = resource_path("levels", f"chamber_{number:02}.json")
    data = json.loads(path.read_text())
    hints = load_hints(data["hints"])
    assert len(hints) == len(data["hints"]) >= 2
    assert load_hints(None) == ()
