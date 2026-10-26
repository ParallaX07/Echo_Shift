"""Bars, room and console drawer geometry at the acceptance display sizes."""

import pytest
import pyxel

from echo_shift.engine.loader import load
from echo_shift.engine.model import initial_state
from echo_shift.engine.recording import act, enter
from echo_shift.engine.turn import Move, Wait
from echo_shift.paths import resource_path
from echo_shift.ui import bars, controls
from echo_shift.ui.hud import model
from echo_shift.ui.layout import (
    Layout,
    char_width,
    elide,
    framed_bounds,
    route_bounds,
    text_width,
)

SIZES = [(1280, 720), (1536, 864), (1920, 1080), (2560, 1080), (640, 480)]
CHAMBERS = [load(resource_path("levels", f"chamber_0{n}.json")) for n in range(1, 7)]


def intersects(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def inside(inner, outer):
    x, y, w, h = inner
    ox, oy, ow, oh = outer
    return ox <= x and oy <= y and x + w <= ox + ow and y + h <= oy + oh


def route_rect(layout, chamber, console):
    min_x, min_y, max_x, max_y = framed_bounds(chamber)
    cell, fit_x, fit_y = layout.room_fit(max_x - min_x + 1, max_y - min_y + 1, console)
    left, top, right, bottom = route_bounds(chamber)
    return (
        fit_x + (left - min_x) * cell,
        fit_y + (top - min_y) * cell,
        (right - left + 1) * cell,
        (bottom - top + 1) * cell,
    )


@pytest.mark.parametrize("width,height", SIZES)
def test_bars_and_room_stack_without_overlap(width, height):
    layout = Layout.fit(width, height)
    assert layout.top[1] == 0
    assert layout.room[1] == layout.top[1] + layout.top[3]
    assert layout.bottom[1] == layout.room[1] + layout.room[3]
    assert layout.bottom[1] + layout.bottom[3] == height
    assert layout.room_w == width and layout.room_h > height // 2
    for rows in (layout.top_rows(), layout.bottom_rows()):
        bar = layout.top if rows == layout.top_rows() else layout.bottom
        assert all(inside(row, bar) for row in rows)
        assert not intersects(*rows)
    x, y, w, h = layout.overlay()
    assert inside((x, y, w, h), layout.room)


def test_bars_grow_with_text_scale():
    heights = [Layout.fit(1920, 1080, scale).top[3] for scale in (1, 2, 3)]
    assert heights == sorted(set(heights))


@pytest.mark.parametrize("width,height", SIZES)
@pytest.mark.parametrize("chamber", CHAMBERS, ids=lambda c: f"{len(c.circuits)}c")
def test_room_fit_keeps_route_clear_of_bars_and_drawer(width, height, chamber):
    layout = Layout.fit(width, height)
    drawer = layout.console_drawer()
    assert inside(drawer, layout.room)
    for console in (False, True):
        route = route_rect(layout, chamber, console)
        assert inside(route, layout.room)
        assert not intersects(route, layout.top) and not intersects(
            route, layout.bottom
        )
        assert console is False or not intersects(route, drawer)
    min_x, min_y, max_x, max_y = framed_bounds(chamber)
    cell = layout.room_fit(max_x - min_x + 1, max_y - min_y + 1)[0]
    assert cell * (max_x - min_x + 1) <= layout.room_w
    assert cell * (max_y - min_y + 1) <= layout.room_h
    assert cell + 1 > layout.room_h // (max_y - min_y + 1) or cell + 1 > (
        layout.room_w // (max_x - min_x + 1)
    )


def states(chamber):
    prepare = initial_state(chamber)
    recording = enter(prepare)
    for move in (Move(1, 0), Wait()):
        result = act(recording, move)
        recording = getattr(result, "state", recording)
    return [prepare, recording, enter(recording)]


def all_items(layout, chamber):
    for state in states(chamber):
        actions = controls.available_actions(state, "game", None, undoable=True)
        hud = model(state)
        count = chamber.max_turns
        yield (
            bars.top_items(
                layout,
                hud,
                level=3,
                name="POWER ALLOCATION",
                step=controls.find(actions, "echo").reason or "Enter Record",
                hints="HINTS 0/3",
                muted=True,
            ),
            layout.top_rows(),
            layout.top,
        )
        yield (
            bars.bottom_items(
                layout, hud, actions, count=count, counter=f"TURNS LEFT {count}"
            ),
            layout.bottom_rows(),
            layout.bottom,
        )


@pytest.mark.parametrize("width,height", SIZES)
@pytest.mark.parametrize("chamber", CHAMBERS, ids=lambda c: f"{len(c.circuits)}c")
def test_every_bar_label_fits_its_rect(width, height, chamber):
    layout = Layout.fit(width, height)
    for items, rows, bar in all_items(layout, chamber):
        assert items
        for item in items:
            assert inside(item.rect, bar), item
            assert any(inside(item.rect, row) for row in rows), item
            if item.kind not in ("slot", "step"):
                assert item.needs(layout) <= item.rect[2], item
            if item.kind == "step":
                assert text_width(item.label(), layout.text_scale) <= item.rect[2]
        for index, first in enumerate(items):
            for second in items[index + 1 :]:
                assert not intersects(first.rect, second.rect), (first, second)


@pytest.mark.parametrize("scale", [1, 2, 3])
@pytest.mark.parametrize("width,height", [(1920, 1080), (2560, 1080)])
def test_labels_fit_at_each_text_scale(width, height, scale):
    layout = Layout.fit(width, height, scale)
    for chamber in CHAMBERS:
        for items, _, bar in all_items(layout, chamber):
            for item in items:
                assert inside(item.rect, bar)
                if item.kind not in ("slot", "step"):
                    assert item.needs(layout) <= item.rect[2]


@pytest.mark.parametrize("width,height", [(1280, 720), (1920, 1080)])
def test_essential_items_survive_at_common_sizes(width, height):
    layout = Layout.fit(width, height)
    items, _, _ = next(all_items(layout, CHAMBERS[1]))
    kinds = {item.kind for item in items}
    assert {"title", "power", "chip", "safety", "step"} <= kinds
    assert len([item for item in items if item.kind == "chip"]) == 3
    keys = {item.key for item in list(all_items(layout, CHAMBERS[1]))[1][0]}
    assert {f"action:{i}" for i in bars.PRIMARY + bars.SECONDARY} <= keys
    assert {f"timeline:{i}" for i in range(CHAMBERS[1].max_turns)} <= keys


@pytest.mark.parametrize("scale", [1, 2, 3, 4])
def test_text_measure_is_never_narrower_than_the_font(scale):
    font = pyxel.Font(
        str(resource_path("assets", "fonts", "DejaVuSansMono.ttf")),
        max(12, scale * 6 + 4),
    )
    assert char_width(scale) >= font.text_width("M")
    assert text_width("MMMM", scale) >= font.text_width("MMMM")


def test_elide_shortens_to_fit():
    assert elide("short", 200, 1) == "short"
    cut = elide("a" * 40, 10 * char_width(2), 2)
    assert cut.endswith("...") and text_width(cut, 2) <= 10 * char_width(2)
    assert elide("abc", 0, 1) == ""


@pytest.mark.parametrize("width,height", [(1280, 720), (1920, 1080), (640, 480)])
def test_menu_controls_fit_and_do_not_overlap(width, height):
    layout = Layout.fit(width, height)
    controls_ = (layout.start_button(), *layout.chamber_cards(3))
    assert all(
        0 <= x < x + w <= width and 0 <= y < y + h <= height for x, y, w, h in controls_
    )
    cards = layout.chamber_cards(3)
    assert all(
        cards[index][0] + cards[index][2] < cards[index + 1][0] for index in range(2)
    )
    six = layout.chamber_cards(6)
    assert all(
        0 <= x < x + w <= width and 0 <= y < y + h <= height for x, y, w, h in six
    )
    assert six[2][1] < six[3][1]
    for first in range(6):
        for second in range(first + 1, 6):
            ax, ay, aw, ah = six[first]
            bx, by, bw, bh = six[second]
            assert ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay
