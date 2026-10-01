"""Display shortcuts do not enter menus or consume game actions."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from echo_shift.engine.model import Phase
from echo_shift.ui import app


@pytest.mark.parametrize(
    "mode,modal,paused,console,phase",
    [
        ("title", None, False, False, Phase.PREPARE),
        ("levels", None, False, False, Phase.PREPARE),
        ("game", "lesson_choice", False, False, Phase.PREPARE),
        ("game", "step", False, False, Phase.RECORDING),
        ("game", "help", False, True, Phase.PREPARE),
        ("game", None, False, False, Phase.RECORDING),
        ("game", None, False, False, Phase.REPLAY),
        ("game", None, True, False, Phase.PREPARE),
        ("game", None, False, True, Phase.PREPARE),
    ],
)
def test_fullscreen_and_alt_enter_preserve_state(
    tmp_path, monkeypatch, mode, modal, paused, console, phase
):
    real_pyxel = app.pyxel
    keys = {
        name: getattr(real_pyxel, name)
        for name in dir(real_pyxel)
        if name.startswith("KEY_")
    }
    pressed = set()
    held = set()
    calls = []
    window = [1280, 720, False]
    fake = SimpleNamespace(
        **keys,
        colors=[0] * 16,
        width=1280,
        height=720,
        init=lambda *args, **kwargs: None,
        btnp=lambda key, **kwargs: key in pressed,
        btn=lambda key: key in held,
        fullscreen=lambda enabled: calls.append(("fullscreen", enabled)),
        resize=lambda w, h: calls.append(("resize", w, h)),
    )
    monkeypatch.setattr(app, "pyxel", fake)
    monkeypatch.setattr(
        app,
        "Display",
        lambda: SimpleNamespace(
            desktop_size=lambda: (1920, 1080), window=lambda: tuple(window)
        ),
    )
    monkeypatch.setattr(app, "Atlas", lambda: None)
    monkeypatch.setattr(app, "user_data_dir", lambda: tmp_path)
    game = app.Game()
    game.mode, game.modal, game.paused, game.console = mode, modal, paused, console
    game.state = replace(game.state, phase=phase)
    before = game.state
    pressed.add(keys["KEY_F11"])
    game.update()
    pressed.clear()
    assert calls == [("fullscreen", True)]
    assert game.state == before
    assert (game.mode, game.modal, game.paused, game.console) == (
        mode,
        modal,
        paused,
        console,
    )
    window[:] = [1920, 1080, True]
    fake.width, fake.height = 1920, 1080
    game.update()
    assert game.fullscreen
    held.add(keys["KEY_ALT"])
    pressed.add(keys["KEY_RETURN"])
    window[:] = [1280, 720, False]
    game.update()
    assert not game.fullscreen
    assert game.state == before
    assert (game.mode, game.modal, game.paused, game.console) == (
        mode,
        modal,
        paused,
        console,
    )
    held.clear()
    pressed.clear()
    pressed.add(keys["KEY_F11"])
    game.update()
    assert calls[-1] == ("fullscreen", True)
    window[:] = [1920, 1080, True]
    pressed.clear()
    game.update()
    pressed.add(keys["KEY_F11"])
    game.update()
    assert calls[-2:] == [("fullscreen", False), ("resize", 1280, 720)]
    assert game.state == before
