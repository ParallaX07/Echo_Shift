"""Menu pointer, clicks and decorative frames do not change chamber state."""

from types import SimpleNamespace

from echo_shift.ui import app, progress, telemetry


def test_menu_mouse_navigation_and_animation_leave_turns_unchanged(
    tmp_path, monkeypatch
):
    real_pyxel = app.pyxel
    keys = {
        name: getattr(real_pyxel, name)
        for name in dir(real_pyxel)
        if name.startswith("KEY_")
    }
    pressed = set()
    visibility = []
    rectangles = []
    fake = SimpleNamespace(
        **keys,
        MOUSE_BUTTON_LEFT=real_pyxel.MOUSE_BUTTON_LEFT,
        mouse_x=-1,
        mouse_y=-1,
        frame_count=0,
        colors=[0] * 16,
        init=lambda *args, **kwargs: None,
        mouse=lambda visible: visibility.append(visible),
        btnp=lambda key, **kwargs: key in pressed,
        cls=lambda *args: None,
        rect=lambda *args: rectangles.append(args),
        rectb=lambda *args: None,
        text=lambda *args: None,
        pal=lambda *args: None,
    )
    monkeypatch.setattr(app, "pyxel", fake)
    monkeypatch.setattr(app, "Atlas", lambda: SimpleNamespace(draw=lambda *args: None))
    monkeypatch.setattr(
        app,
        "Display",
        lambda: SimpleNamespace(desktop_size=lambda: (1280, 720), window=lambda: None),
    )
    monkeypatch.setattr(app, "user_data_dir", lambda: tmp_path)
    monkeypatch.setattr(progress, "user_data_dir", lambda: tmp_path)
    monkeypatch.setattr(telemetry, "user_data_dir", lambda: tmp_path)
    game = app.Game()
    turns = game.state.turns

    def click(rect):
        fake.mouse_x, fake.mouse_y = rect[0] + rect[2] // 2, rect[1] + rect[3] // 2
        pressed.add(fake.MOUSE_BUTTON_LEFT)
        game.update()
        pressed.clear()

    game.update()
    assert visibility == [False]
    frames = []
    for fake.frame_count in (0, 18, 45, 90):
        rectangles.clear()
        game.draw()
        frames.append(tuple(rectangles))
    assert frames[0] != frames[1]
    assert game.state.turns == turns

    click(game.layout.start_button())
    assert game.mode == "levels"
    cards = game.layout.chamber_cards(app.LEVEL_COUNT)
    click(cards[2])
    assert game.mode == "levels" and game.level_cursor == 3
    frames.clear()
    for fake.frame_count in (0, 18, 45):
        rectangles.clear()
        game.draw()
        frames.append(tuple(rectangles))
    assert frames[0] != frames[1]
    assert game.state.turns == turns

    click(cards[0])
    assert game.mode == "game" and game.level == 1
    assert game.state.turns == turns
    assert visibility[-1] is False

    for name in ("KEY_P", "KEY_L"):
        pressed.add(keys[name])
        game.update()
        pressed.clear()
    game.update()
    assert game.mode == "levels" and visibility[-1] is False
