"""Pyxel-free contents of the top and bottom bars: what is drawn where."""

from dataclasses import dataclass

from echo_shift.ui import controls
from echo_shift.ui.hud import Hud
from echo_shift.ui.layout import Layout, Rect, char_width, elide, text_width

PRIMARY = ("wait", "console", "echo", "undo", "retry", "rerecord", "restart")
SECONDARY = ("guide", "hint", "pause")
PRIORITY = ("pause", "guide", "hint")  # which secondary buttons go last when tight
SLOT_SPRITES = {
    "U": "slot_up",
    "R": "slot_right",
    "D": "slot_down",
    "L": "slot_left",
}


@dataclass(frozen=True)
class Item:
    """One drawn element: `cap` (a key cap or number) then `text`, after `lead`."""

    kind: str
    key: str
    rect: Rect
    text: str = ""
    cap: str = ""
    lead: int = 0
    enabled: bool = True
    on: bool = False

    def label(self) -> str:
        return (
            f"{self.cap} {self.text}"
            if self.cap and self.text
            else self.cap + self.text
        )

    def needs(self, layout: Layout) -> int:
        """Pixels the content wants: padding, lead and the label."""
        return 2 * layout.pad + self.lead + text_width(self.label(), layout.text_scale)


def _specs(
    layout: Layout, specs: list[dict], x: int, limit: int, y: int, h: int
) -> list[Item]:
    """Lay specs out left to right from `x`; the ones that do not fit are dropped."""
    items = []
    for spec in specs:
        item = Item(rect=(x, y, 0, h), **spec)
        width = item.needs(layout)
        if x + width > limit:
            break
        items.append(Item(rect=(x, y, width, h), **spec))
        x += width + layout.pad
    return items


def _right_aligned(
    layout: Layout,
    specs: list[dict],
    left: int,
    right: int,
    y: int,
    h: int,
    priority: list[dict] | None = None,
) -> list[Item]:
    """Place the specs that fit between `left` and `right`, flush against `right`.

    Specs are dropped from the end of `priority` (default: their own order) first.
    """
    kept: list[dict] = []
    used = 0
    for spec in priority or specs:
        width = Item(rect=(0, y, 0, h), **spec).needs(layout)
        if used + width > right - left:
            break
        kept.append(spec)
        used += width + layout.pad
    shown = [spec for spec in specs if spec in kept]
    return _specs(layout, shown, right - used + layout.pad, right, y, h)


def top_items(
    layout: Layout,
    hud: Hud,
    *,
    level: int,
    name: str,
    step: str,
    feedback: str = "",
    hints: str = "",
    muted: bool = False,
) -> list[Item]:
    scale = layout.text_scale
    row1, row2 = layout.top_rows()
    x, y, w, h = row1
    left = [
        {"kind": "title", "key": "state", "cap": f"{level:02}", "text": name},
        {"kind": "power", "key": "power", "text": f"POWER {hud.load}/{hud.capacity}"},
    ] + [
        {
            "kind": "chip",
            "key": "circuit:" + circuit,
            "text": circuit.upper().replace("-", " "),
            "lead": char_width(scale),
            "on": on,
        }
        for circuit, on in hud.circuits
    ]
    items = _specs(layout, left, x, x + w, y, h)
    taken = items[-1].rect[0] + items[-1].rect[2] if items else x
    right = [
        {
            "kind": "safety",
            "key": "safety",
            "text": "SAFE" if hud.safe else "DARK",
            "on": hud.safe,
        },
        {"kind": "hints", "key": "", "text": hints},
    ]
    if muted:
        right.append({"kind": "muted", "key": "", "text": "MUTED"})
    items += _right_aligned(layout, right, taken + layout.pad, x + w, y, h)
    x, y, w, h = row2
    cap = "" if feedback else "NEXT STEP"
    room = w - 2 * layout.pad - (text_width(cap + " ", scale) if cap else 0)
    items.append(
        Item(
            "step",
            "",
            row2,
            elide(feedback or step, room, scale),
            cap,
            on=bool(feedback),
        )
    )
    return items


def bottom_items(
    layout: Layout,
    hud: Hud,
    actions: list[controls.Action],
    *,
    count: int,
    counter: str,
) -> list[Item]:
    scale = layout.text_scale
    row_a, row_b = layout.bottom_rows()
    x, y, w, h = row_a
    reserve = (
        text_width(max(counter, f"TURNS LEFT {count}", key=len), scale) + 2 * layout.pad
    )
    gap = max(2, layout.pad // 2)
    slot = max(1, min(layout.slot, (w - reserve - (count - 1) * gap) // count))
    items = []
    for index, (kind, current, direction) in enumerate(hud.timeline[:count]):
        sprite = (
            "slot_wait"
            if kind == "wait"
            else SLOT_SPRITES[direction]
            if kind == "move"
            else "slot_empty"
        )
        items.append(
            Item(
                "slot",
                f"timeline:{index}",
                (x + index * (slot + gap), y + (h - slot) // 2, slot, slot),
                sprite,
                f"{index + 1:02}" if kind == "empty" else "",
                on=current,
            )
        )
    width = text_width(counter, scale) + 2 * layout.pad
    items.append(Item("counter", "", (x + w - width, y, width, h), counter))
    x, y, w, h = row_b
    by_id = {action.id: action for action in actions}

    def spec(action_id: str) -> dict:
        action = by_id[action_id]
        return {
            "kind": "button",
            "key": "action:" + action_id,
            "cap": action.key,
            "text": action.short or action.label,
            "enabled": action.enabled,
        }

    buttons = _specs(layout, [spec(i) for i in PRIMARY if i in by_id], x, x + w, y, h)
    taken = buttons[-1].rect[0] + buttons[-1].rect[2] if buttons else x
    shown = [spec(i) for i in SECONDARY if i in by_id]
    priority = [spec(i) for i in PRIORITY if i in by_id]
    return (
        items
        + buttons
        + _right_aligned(layout, shown, taken + layout.pad, x + w, y, h, priority)
    )
