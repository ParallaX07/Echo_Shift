"""Room and panel geometry at the acceptance display sizes."""

import pytest

from echo_shift.ui.layout import Layout


@pytest.mark.parametrize(
    "width,height", [(1280, 720), (1366, 768), (1920, 1080), (1920, 1200), (3440, 1440)]
)
def test_room_and_timeline_fit(width, height):
    layout = Layout.fit(width, height)
    assert layout.room_w == 12 * layout.cell
    assert layout.room_h == 9 * layout.cell
    assert layout.room_x == 0
    assert 0 <= layout.room_y and layout.room_y + layout.room_h <= height
    assert layout.panel_x == layout.room_w
    assert layout.panel_x + layout.panel_w == width
    assert layout.panel_w > 0
    slots = layout.timeline_slots()
    assert len(slots) == 12
    assert len({x for x, _, _ in slots}) == 3
    assert len({y for _, y, _ in slots}) == 4
    assert all(
        layout.panel_x <= x and x + size <= width and 0 <= y and y + size <= height
        for x, y, size in slots
    )
    compact = layout.timeline_slots(6)
    assert len(compact) == 6
    assert len({y for _, y, _ in compact}) == 2
    assert all(
        layout.panel_x <= x and x + size <= width and 0 <= y and y + size <= height
        for x, y, size in compact
    )
    x, y, w, h = layout.overlay()
    assert 0 <= x and 0 <= y and x + w <= width and y + h <= height


@pytest.mark.parametrize("width,height", [(1280, 720), (1920, 1080), (640, 480)])
def test_menu_controls_fit_and_do_not_overlap(width, height):
    layout = Layout.fit(width, height)
    controls = (layout.start_button(), *layout.chamber_cards(3))
    assert all(
        0 <= x < x + w <= width and 0 <= y < y + h <= height for x, y, w, h in controls
    )
    cards = layout.chamber_cards(3)
    assert all(
        cards[index][0] + cards[index][2] < cards[index + 1][0] for index in range(2)
    )
    future_cards = layout.chamber_cards(6)
    assert all(0 <= y < y + h <= height for _, y, _, h in future_cards)
    assert future_cards[2][1] < future_cards[3][1]
