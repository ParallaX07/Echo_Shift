"""Drive the real Game loop on a real, headless Pyxel window.

Pyxel can be initialised only once per process, so the first test that needs a
window creates it and every later `Game` reuses it: `pyxel.init` is replaced by
a function that initialises once and afterwards does nothing. The fake-Pyxel
unit tests replace `app.pyxel` for their own duration, so the two kinds of test
never see each other's module state.

A frame is `update`, `draw`, then `pyxel.flip()`. `set_btn` takes effect at once
for both `btn` and `btnp`; `flip` ends the frame and so clears the "pressed this
frame" edge. A key press is therefore: set, run a frame, release, run a frame.
"""

import atexit
from types import SimpleNamespace

import pytest
import pyxel

from echo_shift.ui import app, progress, telemetry

FPS = 1000  # Pyxel sleeps in flip() to hold the frame rate; keep the tests quick
OFFSCREEN = (-1, -1)
_real_init = pyxel.init
_window: list[bool] = []


def init_once(width, height, *args, **kwargs):
    """Stand-in for pyxel.init: open the headless window once, then reuse it."""
    if not _window:
        kwargs.update(headless=True, fps=FPS)
        _real_init(width, height, *args, **kwargs)
        _window.append(True)
    elif (pyxel.width, pyxel.height) != (width, height):
        pyxel.resize(width, height)


class Driver:
    """Frame stepping and input injection for one Game on the shared window."""

    def __init__(self, game: app.Game, directory) -> None:
        self.game = game
        self.directory = directory

    def frame(self, count: int = 1) -> None:
        for _ in range(count):
            self.game.update()
            self.game.draw()
            pyxel.flip()

    def press(self, name: str) -> None:
        """Tap a key: down for one frame, then released for one frame."""
        key = getattr(pyxel, "KEY_" + name)
        pyxel.set_btn(key, True)
        self.frame()
        pyxel.set_btn(key, False)
        self.frame()

    def move_to(self, x: int, y: int) -> None:
        pyxel.set_mouse_pos(x, y)
        self.frame()

    def click_at(self, x: int, y: int, button: str = "LEFT") -> None:
        """Hover for a frame, then press and release a mouse button at pixel (x, y)."""
        key = getattr(pyxel, "MOUSE_BUTTON_" + button)
        self.move_to(x, y)
        pyxel.set_btn(key, True)
        self.frame()
        pyxel.set_btn(key, False)
        self.frame()
        self.move_to(*OFFSCREEN)

    def click(self, rect, button: str = "LEFT") -> None:
        x, y, width, height = rect
        self.click_at(x + width // 2, y + height // 2, button)

    def hit(self, key: str):
        """The rect last drawn for a ui_hits key."""
        return next(rect for rect, hit in self.game.ui_hits if hit == key)

    def click_key(self, key: str, button: str = "LEFT") -> None:
        self.click(self.hit(key), button)

    def click_tile(self, x: int, y: int) -> None:
        cell, origin_x, origin_y = self.game.room_view
        self.click_at(origin_x + x * cell + cell // 2, origin_y + y * cell + cell // 2)

    def pixel(self, x: int, y: int) -> int:
        return pyxel.pget(x, y)


@pytest.fixture
def real(tmp_path, monkeypatch):
    """A fresh Game on the shared headless window, with its data in tmp_path."""
    monkeypatch.setattr(pyxel, "init", init_once)
    monkeypatch.setattr(
        app,
        "Display",
        lambda: SimpleNamespace(desktop_size=lambda: (1920, 1080), window=lambda: None),
    )
    for module in (app, progress, telemetry):
        monkeypatch.setattr(module, "user_data_dir", lambda: tmp_path)
    game = app.Game()
    pyxel.set_mouse_pos(*OFFSCREEN)
    atexit.unregister(game.finish_attempt)  # the data directory will be gone by then
    yield Driver(game, tmp_path)
    game.finish_attempt()
    pyxel.set_mouse_pos(*OFFSCREEN)


def room_extent(game: app.Game) -> tuple[int, int, int, int]:
    """Pixel rect (left, top, right, bottom) of the tiles the last draw laid out."""
    cell, origin_x, origin_y = game.room_view
    min_x, min_y, max_x, max_y = game.room_bounds
    return (
        origin_x + min_x * cell,
        origin_y + min_y * cell,
        origin_x + (max_x + 1) * cell,
        origin_y + (max_y + 1) * cell,
    )


def assert_bars_intact(driver: Driver) -> None:
    """The bars are painted whole on the screen and the room stays between them."""
    game = driver.game
    layout = game.layout
    edge = max(1, layout.text_scale // 2)
    _, top_y, width, top_h = layout.top
    _, bottom_y, _, bottom_h = layout.bottom
    xs = range(0, width, 37)
    for x in xs:
        assert driver.pixel(x, top_y) == 1
        assert driver.pixel(x, top_y + top_h - edge) == 12  # top bar's lower edge
        assert driver.pixel(x, bottom_y) == 5  # bottom bar's upper edge
        assert driver.pixel(x, bottom_y + bottom_h - 1) == 1
    left, top, right, bottom = room_extent(game)
    assert layout.room_y <= top and bottom <= bottom_y
    assert 0 <= left and right <= width
