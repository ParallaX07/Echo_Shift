"""Drive menu and tutorial inputs without opening a graphics window."""

import json
from types import SimpleNamespace

from echo_shift.ui import app, progress, telemetry


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
    )
    monkeypatch.setattr(app, "pyxel", fake)
    monkeypatch.setattr(app, "Atlas", lambda: SimpleNamespace(draw=lambda *args: None))
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
    assert game.mode == "game" and game.modal == "tutorial"
    assert "PLAYTEST LOG" not in "".join(drawn_text)
    assert game.room_view[0] > game.layout.cell
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
    drawn_text.clear()
    press("P")
    assert game.paused
    assert "PLAYTEST LOG" not in "".join(drawn_text)
    press("P")
    press("C")
    assert not game.paused
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
    assert game.mode == "levels"
    press("RETURN")
    assert game.level == 2 and game.modal == "tutorial"
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
