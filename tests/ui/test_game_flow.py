"""Drive menu and tutorial inputs without opening a graphics window."""

import json
from types import SimpleNamespace

from echo_shift.ui import app, cuedraw, progress, telemetry


def test_first_chamber_unlocks_second_and_navigation_works(tmp_path, monkeypatch):
    real_pyxel = app.pyxel
    keys = {
        name: getattr(real_pyxel, name)
        for name in dir(real_pyxel)
        if name.startswith("KEY_")
    }
    pressed = set()
    drawn_text = []
    fake = SimpleNamespace(
        **keys,
        colors=[0] * 16,
        init=lambda *args, **kwargs: None,
        btnp=lambda key, **kwargs: key in pressed,
        cls=lambda *args: None,
        rect=lambda *args: None,
        rectb=lambda *args: None,
        text=lambda *args: drawn_text.append(args[2]),
        pal=lambda *args: None,
        line=lambda *args: None,
        tri=lambda *args: None,
        trib=lambda *args: None,
        circ=lambda *args: None,
        circb=lambda *args: None,
        dither=lambda *args: None,
        clip=lambda *args: None,
    )
    monkeypatch.setattr(app, "pyxel", fake)
    monkeypatch.setattr(cuedraw, "pyxel", fake)
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
    assert game.mode == "game" and game.modal == "lesson_choice"
    assert "PLAYTEST LOG" not in "".join(drawn_text)
    cell, origin_x, origin_y = game.room_view
    left, top, right, bottom = game.room_bounds
    # The chamber is taller than the room band, so it fills the band and scrolls.
    assert origin_y + top * cell <= game.layout.room_y
    assert origin_y + (bottom + 1) * cell >= game.layout.room_y + game.layout.room_h
    assert (
        0 <= origin_x + left * cell
        and origin_x + (right + 1) * cell <= game.layout.width
    )
    press("H")
    assert game.modal == "guide" and len(game.seen_hints) == 1
    press("RETURN")
    press("F")
    for _ in range(3):
        press("LEFT")  # the console is a few tiles from the start
    press("E")
    press("SPACE")
    press("RETURN")
    assert game.state.powered_circuits == frozenset({"lift-power"})
    for _ in range(3):
        press("RIGHT")
    press("RETURN")
    press("RETURN")
    press("RETURN")
    for _ in range(4):
        press("RIGHT")
    press("DOWN")
    press("DOWN")
    assert game.modal == "result"
    assert game.unlocked == 2
    assert progress.load(3).unlocked == 2
    press("RETURN")
    assert game.level == 2 and game.modal == "lesson_choice"
    press("F")
    press("M")
    assert game.muted
    drawn_text.clear()
    press("P")
    assert game.paused
    assert "PLAYTEST LOG" not in "".join(drawn_text)
    press("P")
    press("C")
    assert not game.paused
    for _ in range(2):
        press("LEFT")
    press("E")
    press("SPACE")
    press("DOWN")
    press("SPACE")
    press("DOWN")
    press("SPACE")
    press("RETURN")
    assert game.attempt.unsafe_power_choices == 1
    press("E")
    press("L")
    assert game.mode == "game"  # L is only a pause-menu key.
    press("P")
    press("L")
    assert game.mode == "levels"
    press("RETURN")
    assert game.level == 2 and game.modal == "lesson_choice"
    press("P")
    press("L")
    records = [
        json.loads(line)
        for line in (tmp_path / "playtest.jsonl").read_text().splitlines()
    ]
    assert [record["chamber"] for record in records] == [1, 2, 2]
    assert records[0]["completed"] and records[0]["hints"] == 1
    assert records[0]["completion_time_seconds"] is not None
    assert not records[1]["completed"] and records[1]["resets"] == 1
    assert records[1]["unsafe_power_choices"] == 1
