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
    x, y, w, h = layout.overlay()
    assert 0 <= x and 0 <= y and x + w <= width and y + h <= height
