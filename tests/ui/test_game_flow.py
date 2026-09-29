"""Drive menu and tutorial inputs without opening a graphics window."""

from types import SimpleNamespace

from echo_shift.ui import app, progress


def test_first_chamber_unlocks_second_and_navigation_works(tmp_path, monkeypatch):
    real_pyxel = app.pyxel
    keys = {
        name: getattr(real_pyxel, name)
        for name in dir(real_pyxel)
        if name.startswith("KEY_")
    }
    pressed = set()
    fake = SimpleNamespace(
        **keys,
        colors=[0] * 16,
        init=lambda *args, **kwargs: None,
        btnp=lambda key, **kwargs: key in pressed,
        cls=lambda *args: None,
        rect=lambda *args: None,
        rectb=lambda *args: None,
        text=lambda *args: None,
        pal=lambda *args: None,
    )
    monkeypatch.setattr(app, "pyxel", fake)
    monkeypatch.setattr(app, "Atlas", lambda: SimpleNamespace(draw=lambda *args: None))
    monkeypatch.setattr(app, "user_data_dir", lambda: tmp_path)
    monkeypatch.setattr(progress, "user_data_dir", lambda: tmp_path)
    game = app.Game()

    def press(name):
        pressed.add(keys[f"KEY_{name}"])
        game.update()
        game.draw()
        pressed.clear()

    assert game.mode == "title"
    game.draw()
    press("RETURN")
    assert game.mode == "levels"
    press("DOWN")
    press("RETURN")
    assert game.mode == "levels"  # Chamber 2 is locked.
    press("UP")
    press("RETURN")
    assert game.mode == "game" and game.modal == "tutorial"
    press("H")
    assert game.modal == "hint" and len(game.seen_hints) == 1
    press("RETURN")
    press("E")
    press("SPACE")
    press("RETURN")
    assert game.state.powered_circuits == frozenset({"lift-power"})
    press("RETURN")
    press("RETURN")
    press("Q")
    press("RIGHT")
    press("RIGHT")
    assert game.modal == "result"
    assert game.unlocked == 2
    assert progress.load_unlocked(3) == 2
    press("RETURN")
    assert game.level == 2 and game.modal == "tutorial"
    press("RETURN")
    press("M")
    assert game.muted
    press("P")
    assert game.paused
    press("P")
    press("C")
    assert not game.paused
    press("L")
    assert game.mode == "levels"
    press("RETURN")
    assert game.level == 2 and game.modal == "tutorial"
