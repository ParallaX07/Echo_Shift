"""Gamepad play: every button is read through the action model, like the keys."""

from types import SimpleNamespace

import pyxel

from echo_shift.engine.model import Phase
from echo_shift.ui import app, controls, motion


def play(player, number=1):
    player.game.open_level(number)
    player.press("F")
    return player.game


def hold_pad(player, name, frames):
    """Hold a pad button for `frames` updates; return the player's tile after each."""
    button = getattr(pyxel, "GAMEPAD1_BUTTON_" + name)
    tiles = []
    player.held.add(button)
    for index in range(frames):
        if index == 0:
            player.pressed.add(button)
        player.game.update()
        player.game.draw()
        player.pressed.discard(button)
        tiles.append(player.game.state.player)
    player.held.discard(button)
    return tiles


def test_the_echo_button_records_saves_and_launches(player):
    game = play(player)
    assert game.state.phase is Phase.PREPARE
    player.press_pad("X")
    assert game.state.phase is Phase.RECORDING


def test_a_waits_only_while_a_turn_can_be_spent(player):
    game = play(player)
    player.press_pad("A")
    assert not game.state.recording  # nothing to spend a turn on yet
    player.press_pad("X")
    player.press_pad("A")
    assert len(game.state.recording) == 1


def test_the_dpad_moves_and_b_undoes(player):
    game = play(player)
    start = game.state.player
    player.press_pad("DPAD_LEFT")
    assert game.state.player.x == start.x - 1
    player.press_pad("B")
    assert game.state.player == start


def test_holding_the_dpad_walks_as_each_glide_lands(player):
    game = play(player)
    first = game.state.player
    tiles = hold_pad(player, "DPAD_LEFT", motion.WALK_FRAMES + 5)
    moved = [
        frame
        for frame, (before, now) in enumerate(zip([first, *tiles], tiles))
        if before != now
    ]
    assert moved == [0, motion.WALK_FRAMES]


def test_y_opens_and_closes_the_console_and_the_console_reads_the_pad(player):
    game = play(player)
    player.to_console()
    player.press_pad("Y")
    assert game.console
    player.press_pad("DPAD_DOWN")
    assert game.selection == (1 % len(game.state.chamber.circuits))
    before = game.pending
    player.press_pad("A")  # toggles the selected circuit
    assert game.pending != before
    player.press_pad("B")
    assert not game.console


def test_b_backs_out_of_the_console_instead_of_undoing(player):
    game = play(player)
    player.to_console()
    spot = game.state.player
    player.press_pad("Y")
    player.press_pad("B")
    assert not game.console and game.state.player == spot


def test_start_pauses_and_the_menu_takes_the_pad(player):
    game = play(player)
    player.press_pad("START")
    assert game.paused and game.pause_index == 0
    player.press_pad("DPAD_DOWN")
    assert game.pause_index == 1
    player.press_pad("B")  # B closes, it does not undo
    assert not game.paused
    player.press_pad("START")
    player.press_pad("START")
    assert not game.paused
    player.press_pad("START")
    game.pause_index = app.PAUSE_ITEMS.index("settings")
    player.press_pad("A")
    assert game.settings_open
    player.press_pad("B")
    assert game.paused and not game.settings_open


def test_back_opens_the_guide_and_the_dpad_turns_its_pages(player):
    game = play(player)
    player.press_pad("BACK")
    assert game.modal == "guide"
    page = game.guide_page
    player.press_pad("DPAD_RIGHT")
    assert game.guide_page == page + 1
    player.press_pad("B")
    assert game.modal is None


def test_menus_take_the_pad(player):
    game = player.game
    player.press_pad("A")
    assert game.mode == "levels"
    player.press_pad("A")
    assert game.mode == "game"
    player.press_pad("A")  # start the guided lesson
    assert game.modal is None and game.lesson is not None


def test_labels_show_pad_glyphs_after_pad_use_and_keys_after_key_use(player):
    game = play(player)
    player.press("DOWN")
    assert controls.find(game.bar_actions(), "wait").key == "Space"
    player.press_pad("DPAD_LEFT")
    assert controls.pad_in_use()
    bar = {action.id: action.key for action in game.bar_actions()}
    assert bar["wait"] == "A" and bar["undo"] == "B" and bar["echo"] == "X"
    assert bar["pause"] == "Start" and bar["guide"] == "Back"
    assert bar["restart"] == "C"  # no pad button: the key still works
    game.draw()
    assert "A" in player.drawn and "Start" in player.drawn
    player.press("DOWN")
    assert not controls.pad_in_use()
    assert controls.find(game.bar_actions(), "wait").key == "Space"


def test_text_that_names_keys_follows_the_device(player):
    game = play(player)
    assert controls.resolve("Press {key:echo}") == "Press Enter"
    player.press_pad("DPAD_LEFT")
    assert controls.resolve("Press {key:echo}") == "Press X"
    assert controls.resolve("Use {key:move}") == "Use the D-pad"
    lines = controls.controls_lines(game.level)
    assert lines[0] == "the D-pad: Move one tile"
    assert "A: Wait one turn" in lines


def test_the_mouse_counts_as_the_keyboard_device(player):
    play(player)
    player.press_pad("DPAD_LEFT")
    assert controls.pad_in_use()
    player.click_at(5, 5)
    assert not controls.pad_in_use()


def test_the_crt_setting_switches_the_screen_mode_and_is_saved(player):
    game = play(player)
    assert player.modes == [app.SCREEN_CRISP]  # default off
    player.press("P")
    game.pause_index = app.PAUSE_ITEMS.index("settings")
    player.press("RETURN")
    game.settings_index = app.SETTINGS_ITEMS.index("crt")
    assert game.settings_value("crt") == "OFF"
    player.press("RETURN")
    assert game.progress.settings.crt and player.modes[-1] == app.SCREEN_RETRO
    player.press("RETURN")
    assert not game.progress.settings.crt and player.modes[-1] == app.SCREEN_CRISP
    player.press("RETURN")
    from echo_shift.ui import progress

    assert progress.load(6, player.directory).settings.crt


def test_the_window_icon_is_cut_from_the_player_sprite(player):
    game = player.game
    entry = {"u": 4, "v": 8, "width": 96, "height": 96}
    seen = []

    def pget(x, y):
        seen.append((x, y))
        return 9 if 40 <= x - 4 < 60 and 30 <= y - 8 < 80 else 0

    game.atlas = SimpleNamespace(
        entries={app.ICON_SPRITE: entry}, image=SimpleNamespace(pget=pget)
    )
    game.set_icon()
    (rows, scale, colkey) = player.icons[-1]
    assert len(rows) == app.ICON_SIZE and scale == app.ICON_SCALE and colkey == 0
    assert all(len(row) == app.ICON_SIZE for row in rows)
    assert set("".join(rows)) == {"0", "9"}
    assert min(x for x, _ in seen) >= 4 and min(y for _, y in seen) >= 8


def test_a_missing_icon_never_stops_the_game(player):
    player.game.atlas = SimpleNamespace(entries={})
    player.game.set_icon()
    assert player.icons == []
