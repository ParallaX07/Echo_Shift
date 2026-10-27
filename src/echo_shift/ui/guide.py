"""Pyxel-free guide pages: what each page says, built from the action model."""

from echo_shift.engine.model import Position, State
from echo_shift.ui import controls
from echo_shift.ui.help import room_info
from echo_shift.ui.story import Terminal

PAGES = (
    ("goal", "GOAL"),
    ("controls", "CONTROLS"),
    ("objects", "OBJECTS"),
    ("echo", "ECHO"),
    ("power", "POWER"),
    ("hints", "HINTS"),
    ("rules", "PRECISE RULES"),
)
PAGE_IDS = tuple(page for page, _ in PAGES)

GOAL = (
    "Reach the elevator and stand on it while it is running.",
    (
        "An elevator or gate works only when its circuit has power AND its linked pad "
        "is active. Pads carry letters so you can match them to their machines."
    ),
    (
        "Every turn you take must end on a lit tile or in the hub. A dark tile ends "
        "the attempt."
    ),
    (
        "Outside the hub you can only move while recording or while your echo runs: "
        "press {key:echo} at the hub to record, {key:echo} again to save, and "
        "{key:echo} at the hub to launch."
    ),
)
ECHO = (
    (
        "The blue echo repeats the moves and waits you recorded, one per turn, "
        "starting from the hub tile where you began recording."
    ),
    (
        "It can stand on pads, share your tile and walk through darkness. It cannot "
        "supply power or work a console, and walls and closed gates stop it."
    ),
    (
        "At the hub, {key:echo} starts a recording, saves it, and later launches the "
        "echo. {label:rerecord} throws a recording away, {label:retry} runs the echo "
        "again from launch, and {key:undo} takes back your last input."
    ),
    (
        "Once a recording is saved, the bottom bar shows each recorded turn. "
        "{key:preview_prev} and {key:preview_next} step through them to preview "
        "where the echo will be."
    ),
)
POWER = (
    (
        "The generator can run a limited amount at once. This is a limit, not a "
        "battery: nothing drains while the circuits stay on."
    ),
    (
        "Stand on the hub console and press {key:console} to open the console. "
        "{key:nav_prev}/{key:nav_next} choose a circuit and {key:toggle} switches it."
    ),
    (
        "Before recording and after saving, a switch takes effect at once and costs "
        "no turn. During a recording or replay, changes wait for {key:apply} and cost "
        "one turn."
    ),
    (
        "A choice that is over budget is refused whole. Nothing changes and no turn "
        "passes."
    ),
)
RULES = (
    (
        "A turn passes for each accepted move, wait or power change made during a "
        "recording or replay. Menus, hovering and reading never pass a turn."
    ),
    (
        "Each turn runs in this order: the echo leaves if its time is up and pads "
        "refresh; a power change is applied; you and the echo move, using gates as "
        "they stand; pads and gates update for the next turn; then safety and the "
        "exit are checked."
    ),
    (
        "Rejected inputs cost nothing. Walking into a wall or a closed gate, an "
        "over-budget power choice, or a full recording changes nothing: no turn "
        "passes, nothing is recorded and the echo does not move."
    ),
    (
        "If a recorded command is blocked, the echo uses it up and stays where it "
        "is. It never retries and never fails the attempt."
    ),
    (
        "After its last command the echo holds its final tile for one extra turn, "
        "then leaves at the start of the turn after that."
    ),
    (
        "A power change during a recording or replay costs a turn and takes effect "
        "that same turn, so it counts for that turn's safety check."
    ),
    (
        "A gate or elevator is open or running when its circuit has power and its "
        "pad is active. The state is recomputed after the echo leaves, after a power "
        "change, and again after pads update."
    ),
    (
        "A pad is active while a body stands on it. A timed pad stays active for its "
        "countdown after the last body leaves."
    ),
    (
        "Launching resets pads and your position, keeps the power and the recording, "
        "and creates the echo at its start. {label:retry} returns to that moment."
    ),
)


def title(page: str) -> str:
    return dict(PAGES)[page]


def objects(state: State, terminals: tuple[Terminal, ...] = ()) -> list[str]:
    """Plain object notes plus the live explanation of each pad and machine."""
    notes = [
        "YOU: the amber technician. Your tile must be lit at the end of every turn.",
        "ECHO: the blue copy that replays your recording.",
        "HUB: always lit and safe. Moving inside it before a launch is free.",
        (
            f"HUB CONSOLE: stand on it and press {controls.key_text('console')} to choose "
            "which circuits are on."
        ),
        (
            "LIT AND DARK FLOOR: dark tiles are unsafe to end a turn on; the echo "
            "ignores darkness."
        ),
    ]
    if terminals:
        notes.insert(
            4,
            (
                f"LOG TERMINAL: press {controls.key_text('console')} on or next to one "
                "to read it. Reading is free and changes nothing."
            ),
        )
    chamber = state.chamber
    seen: list[Position] = [pad.position for pad in chamber.pads]
    seen += [device.position for device in chamber.devices]
    for position in seen:
        title_text, detail = room_info(state, position, lighting_notes=False)
        notes.append(f"{title_text}: {detail}")
    return notes


def hints(revealed: tuple[str, ...], total: int) -> list[str]:
    lines = [f"{number}. {hint}" for number, hint in enumerate(revealed, 1)]
    left = total - len(revealed)
    if not total:
        lines.append("This chamber has no hints.")
    elif left:
        lines.append(
            f"{left} more hint{'s' if left != 1 else ''} left. "
            "Press {key:hint} to reveal the next one."
        )
    else:
        lines.append("No more hints in this chamber.")
    return lines


def page_lines(
    page: str,
    state: State,
    *,
    level: int,
    revealed: tuple[str, ...] = (),
    total_hints: int = 0,
    terminals: tuple[Terminal, ...] = (),
) -> list[str]:
    """The lines of one page, with key placeholders already filled in."""
    if page == "goal":
        lines = list(GOAL)
    elif page == "controls":
        lines = controls.controls_lines(level)
    elif page == "objects":
        lines = objects(state, terminals)
    elif page == "echo":
        lines = list(ECHO)
    elif page == "power":
        lines = list(POWER)
    elif page == "hints":
        lines = hints(revealed, total_hints)
    elif page == "rules":
        lines = list(RULES)
    else:
        raise KeyError(page)
    return [controls.resolve(line) for line in lines]
