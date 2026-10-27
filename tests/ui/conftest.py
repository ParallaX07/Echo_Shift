"""Fake-Pyxel fixtures that drive the real Game loop without a window."""

from types import SimpleNamespace

import pytest

from echo_shift.ui import app, controls, cuedraw, progress, telemetry


@pytest.fixture(autouse=True)
def keyboard_labels():
    """Labels follow the last input device, a process-wide setting: reset it."""
    controls.set_device("keys")
    yield
    controls.set_device("keys")


@pytest.fixture
def player(tmp_path, monkeypatch):
    real = app.pyxel
    keys = {name: getattr(real, name) for name in dir(real) if name.startswith("KEY_")}
    pad = {
        name: getattr(real, name)
        for name in dir(real)
        if name.startswith("GAMEPAD1_BUTTON_")
    }
    held, pressed = set(), set()
    drawn, played, modes, icons = [], [], [], []
    fake = SimpleNamespace(
        **keys,
        **pad,
        screen_mode=modes.append,
        icon=lambda *a: icons.append(a),
        MOUSE_BUTTON_LEFT=real.MOUSE_BUTTON_LEFT,
        MOUSE_BUTTON_RIGHT=real.MOUSE_BUTTON_RIGHT,
        mouse_x=-1,
        mouse_y=-1,
        colors=[0] * 16,
        init=lambda *a, **k: None,
        Sound=real.Sound,
        play=lambda ch, snd, **kw: played.append((ch, snd, kw)),
        stop=lambda ch=None: None,
        play_pos=lambda ch: None,
        channels=[SimpleNamespace(gain=0.125) for _ in range(4)],
        btn=lambda k: k in held,
        btnp=lambda k, **kwargs: k in pressed,
        cls=lambda *a: None,
        rect=lambda *a: None,
        rectb=lambda *a: None,
        text=lambda *a: drawn.append(a[2]),
        pal=lambda *a: None,
        line=lambda *a: None,
        tri=lambda *a: None,
        trib=lambda *a: None,
        circ=lambda *a: None,
        circb=lambda *a: None,
        pset=lambda *a: None,
        dither=lambda *a: None,
        clip=lambda *a: None,
    )
    monkeypatch.setattr(app, "pyxel", fake)
    monkeypatch.setattr(cuedraw, "pyxel", fake)
    monkeypatch.setattr(
        app, "Atlas", lambda: SimpleNamespace(draw=lambda *a, **k: None)
    )
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

    def press_pad(name, frames=1):
        """Hold a gamepad button (A, DPAD_UP, START ...) for some frames, then release."""
        button = pad["GAMEPAD1_BUTTON_" + name]
        for frame in range(frames):
            held.add(button)
            if frame == 0:
                pressed.add(button)
            game.update()
            game.draw()
            pressed.clear()
        held.discard(button)
        game.update()  # release frame

    def to_console():
        """Walk the hub from the door to the console, as a player does."""
        (console,) = game.state.chamber.consoles
        for _ in range(20):
            if game.state.player == console:
                return
            press("LEFT" if console.x < game.state.player.x else "RIGHT")
        raise AssertionError("the console is not on the door's row")

    def click_at(x, y, button=fake.MOUSE_BUTTON_LEFT):
        """Click pixel (x, y) with a mouse button, as the mouse would after a draw."""
        game.draw()
        fake.mouse_x, fake.mouse_y = x, y
        pressed.add(button)
        game.update()
        game.draw()
        pressed.clear()
        fake.mouse_x = fake.mouse_y = -1
        game.update()

    def click(rect, button=fake.MOUSE_BUTTON_LEFT):
        """Click the centre of a rect."""
        x, y, width, height = rect
        click_at(x + width // 2, y + height // 2, button)

    def click_tile(x, y, button=fake.MOUSE_BUTTON_LEFT):
        """Click the centre of room tile (x, y) at the last drawn room fit."""
        game.draw()
        cell, ox, oy = game.room_view
        click_at(ox + x * cell + cell // 2, oy + y * cell + cell // 2, button)

    def click_row(key):
        """Click the panel row registered under a ui_hits key."""
        game.draw()
        click(next(r for r, hit in game.ui_hits if hit == key))

    def button(action_id):
        """Click the bottom-bar button for an action."""
        game.draw()
        rect = next(r for r, key in game.ui_hits if key == "action:" + action_id)
        click(rect)

    return SimpleNamespace(
        game=game,
        press=press,
        press_pad=press_pad,
        to_console=to_console,
        click=click,
        click_at=click_at,
        click_tile=click_tile,
        click_row=click_row,
        button=button,
        fake=fake,
        pressed=pressed,
        held=held,
        drawn=drawn,
        played=played,
        modes=modes,
        icons=icons,
        directory=tmp_path,
    )
