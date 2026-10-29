"""Pyxel-free action model: key bindings and the actions available right now.

Every key name, button label, tooltip and legend line is derived from this
module, so what the screen says always matches what input handling accepts.
"""

import re
from dataclasses import dataclass

from echo_shift.engine.model import Phase, State
from echo_shift.ui import story


@dataclass(frozen=True)
class Action:
    id: str
    key: str
    label: str
    enabled: bool = True
    reason: str = ""
    short: str = ""


@dataclass(frozen=True)
class Binding:
    id: str
    keys: tuple[str, ...]
    cap: str
    label: str
    hidden: tuple[str, ...] = ()
    short: str = ""
    pad: tuple[str, ...] = ()
    pad_cap: str = ""


RIGHT_CLICK = "MOUSE_BUTTON_RIGHT"


def _names(names: str) -> tuple[str, ...]:
    """Pyxel constant names: plain key names get a KEY_ prefix, mouse ones do not."""
    return tuple(
        name if name.startswith("MOUSE_") else f"KEY_{name}" for name in names.split()
    )


def _pad_names(names: str) -> tuple[str, ...]:
    """Pyxel gamepad constant names: A, B, DPAD_UP, START ... on the first pad."""
    return tuple(f"GAMEPAD1_BUTTON_{name}" for name in names.split())


def _binding(
    id: str,
    keys: str,
    cap: str,
    label: str,
    hidden: str = "",
    short: str = "",
    pad: str = "",
    pad_cap: str = "",
) -> tuple[str, Binding]:
    return id, Binding(
        id, _names(keys), cap, label, _names(hidden), short, _pad_names(pad), pad_cap
    )


BINDINGS: dict[str, Binding] = dict(
    (
        _binding("move_up", "W UP", "W", "Move up", pad="DPAD_UP", pad_cap="D-pad Up"),
        _binding(
            "move_down",
            "S DOWN",
            "S",
            "Move down",
            pad="DPAD_DOWN",
            pad_cap="D-pad Down",
        ),
        _binding(
            "move_left",
            "A LEFT",
            "A",
            "Move left",
            pad="DPAD_LEFT",
            pad_cap="D-pad Left",
        ),
        _binding(
            "move_right",
            "D RIGHT",
            "D",
            "Move right",
            pad="DPAD_RIGHT",
            pad_cap="D-pad Right",
        ),
        _binding("wait", "SPACE", "Space", "Wait", pad="A", pad_cap="A"),
        _binding(
            "console", "E", "E", "Power console", short="Power", pad="Y", pad_cap="Y"
        ),
        _binding("echo", "RETURN F", "Enter", "Echo", hidden="Q", pad="X", pad_cap="X"),
        _binding(
            "undo",
            "Z BACKSPACE",
            "Z",
            "Undo last move",
            short="Undo",
            pad="B",
            pad_cap="B",
        ),
        _binding("retry", "R", "R", "Retry from launch", short="Retry"),
        _binding("restart", "C", "C", "Restart chamber", short="Restart"),
        _binding("rerecord", "", "", "Re-record"),
        _binding(
            "preview_prev",
            "LEFTBRACKET",
            "[",
            "Preview earlier turn",
            pad="LEFTSHOULDER",
            pad_cap="LB",
        ),
        _binding(
            "preview_next",
            "RIGHTBRACKET",
            "]",
            "Preview later turn",
            pad="RIGHTSHOULDER",
            pad_cap="RB",
        ),
        _binding("pause", "ESCAPE P", "Esc", "Pause", pad="START", pad_cap="Start"),
        _binding("guide", "T", "T", "Guide", pad="BACK", pad_cap="Back"),
        _binding("hint", "H", "H", "Next hint", short="Hint"),
        _binding("mute", "M", "M", "Mute"),
        _binding("fullscreen", "F11", "F11", "Fullscreen"),
        _binding(
            "nav_prev",
            "UP W LEFT A",
            "Up",
            "Previous",
            pad="DPAD_UP DPAD_LEFT",
            pad_cap="D-pad Up",
        ),
        _binding(
            "nav_next",
            "DOWN S RIGHT D",
            "Down",
            "Next",
            pad="DPAD_DOWN DPAD_RIGHT",
            pad_cap="D-pad Down",
        ),
        _binding("confirm", "RETURN SPACE", "Enter", "Confirm", pad="A", pad_cap="A"),
        _binding(
            "close",
            f"ESCAPE E {RIGHT_CLICK}",
            "Esc",
            "Close",
            pad="B Y",
            pad_cap="B",
        ),
        _binding("toggle", "SPACE", "Space", "Toggle circuit", pad="A", pad_cap="A"),
        _binding("apply", "RETURN", "Enter", "Apply", pad="X", pad_cap="X"),
        _binding("free_play", "F", "F", "Play freely", pad="X", pad_cap="X"),
        _binding("levels", "L", "L", "Chamber select"),
        _binding("quit_title", "", "", "Quit to title"),
        _binding("settings", "", "", "Settings"),
        _binding("controls", "", "", "Controls"),
        _binding("music_volume", "", "", "Music volume"),
        _binding("sfx_volume", "", "", "SFX volume"),
        _binding("reduced_motion", "", "", "Reduced motion"),
        _binding("crt", "", "", "CRT look"),
        _binding(
            "row_prev", "UP W", "Up", "Previous", pad="DPAD_UP", pad_cap="D-pad Up"
        ),
        _binding(
            "row_next", "DOWN S", "Down", "Next", pad="DPAD_DOWN", pad_cap="D-pad Down"
        ),
        _binding(
            "value_down",
            "LEFT A",
            "Left",
            "Lower",
            pad="DPAD_LEFT",
            pad_cap="D-pad Left",
        ),
        _binding(
            "value_up",
            "RIGHT D",
            "Right",
            "Raise",
            pad="DPAD_RIGHT",
            pad_cap="D-pad Right",
        ),
    )
)

SCOPES: dict[str, tuple[str, ...]] = {
    "title": ("confirm", "mute", "fullscreen"),
    "levels": ("nav_prev", "nav_next", "confirm", "close", "mute", "fullscreen"),
    "play": (
        "move_up",
        "move_down",
        "move_left",
        "move_right",
        "wait",
        "console",
        "echo",
        "undo",
        "retry",
        "restart",
        "rerecord",
        "preview_prev",
        "preview_next",
        "pause",
        "guide",
        "hint",
        "mute",
        "fullscreen",
    ),
    "console": (
        "nav_prev",
        "nav_next",
        "toggle",
        "apply",
        "close",
        "undo",
        "guide",
        "hint",
        "mute",
        "fullscreen",
    ),
    "pause": (
        "nav_prev",
        "nav_next",
        "confirm",
        "pause",
        "undo",
        "retry",
        "restart",
        "rerecord",
        "levels",
        "settings",
        "controls",
        "quit_title",
        "mute",
        "fullscreen",
    ),
    "settings": (
        "row_prev",
        "row_next",
        "value_down",
        "value_up",
        "music_volume",
        "sfx_volume",
        "mute",
        "reduced_motion",
        "crt",
        "fullscreen",
        "close",
    ),
    "failure": ("undo", "retry", "restart", "mute", "fullscreen"),
    "log": ("confirm", "close", "guide", "hint", "mute", "fullscreen"),
    "guide": ("nav_prev", "nav_next", "confirm", "close", "guide", "hint", "mute"),
    "lesson_choice": ("confirm", "free_play", "guide", "hint", "pause", "mute"),
    "result": ("confirm", "close", "restart", "mute"),
}

LABELS: dict[tuple[str, str], str] = {
    ("title", "confirm"): "Start",
    ("levels", "nav_prev"): "Select",
    ("levels", "nav_next"): "Select",
    ("levels", "confirm"): "Play",
    ("levels", "close"): "Title",
    ("pause", "pause"): "Resume",
    ("pause", "confirm"): "Choose",
    ("guide", "nav_prev"): "Previous page",
    ("guide", "nav_next"): "Next page",
    ("guide", "confirm"): "Return",
    ("guide", "close"): "Return",
    ("settings", "close"): "Back",
    ("lesson_choice", "confirm"): "Start guided lesson",
    ("result", "confirm"): "Next chamber",
    ("result", "close"): "Chamber select",
    ("result", "restart"): "Play again",
    ("console", "close"): "Exit",
    ("log", "confirm"): "Next",
    ("log", "close"): "Close",
}

MOVE_DELTAS = {
    "move_up": (0, -1),
    "move_down": (0, 1),
    "move_left": (-1, 0),
    "move_right": (1, 0),
}
MODIFIER_KEYS = ("KEY_ALT", "KEY_LALT", "KEY_RALT")


# B means "back out" inside overlays, so undo gives it up in the console and the
# pause menu (undo stays on the key there, and the bar lists it as such).
PAD_SHADOWED = frozenset({("console", "undo"), ("pause", "undo")})
_device = "keys"


def set_device(device: str) -> None:
    """Remember the last input device ("keys" or "pad"): labels follow it."""
    global _device
    if device not in ("keys", "pad"):
        raise ValueError(f"unknown input device {device!r}")
    _device = device


def pad_in_use() -> bool:
    return _device == "pad"


def key_names(action_id: str) -> tuple[str, ...]:
    """Every key name that triggers an action, hidden aliases included."""
    binding = BINDINGS[action_id]
    return binding.keys + binding.hidden


def pad_names(action_id: str, scope: str | None = None) -> tuple[str, ...]:
    """Gamepad button names that trigger an action in `scope` (any scope if None)."""
    if (scope, action_id) in PAD_SHADOWED:
        return ()
    return BINDINGS[action_id].pad


def cap(action_id: str, scope: str | None = None) -> str:
    """The key cap to print: the pad glyph after pad use, else the key name.

    An action with no pad button there keeps its key cap, which still works.
    """
    binding = BINDINGS[action_id]
    if pad_in_use() and pad_names(action_id, scope) and binding.pad_cap:
        return binding.pad_cap
    return binding.cap


def all_key_names() -> tuple[str, ...]:
    return tuple(dict.fromkeys(n for i in BINDINGS for n in key_names(i)))


def all_pad_names() -> tuple[str, ...]:
    return tuple(dict.fromkeys(n for b in BINDINGS.values() for n in b.pad))


def gameplay_key_names() -> tuple[str, ...]:
    """All keys that can start a gameplay action; held keys must be released."""
    names: list[str] = []
    for action_id in SCOPES["play"] + SCOPES["console"]:
        names.extend(key_names(action_id))
    return tuple(dict.fromkeys(names))


def gameplay_pad_names() -> tuple[str, ...]:
    """All gamepad buttons that can start a gameplay action."""
    names = [
        name
        for scope in ("play", "console")
        for action_id in SCOPES[scope]
        for name in pad_names(action_id, scope)
    ]
    return tuple(dict.fromkeys(names))


def scope_for(screen: str, modal: str | None) -> str:
    if screen != "game":
        return screen
    return modal if modal in SCOPES else "play"


def echo_verb(state: State) -> str | None:
    """What the echo key does now: record, save, launch, or None when disabled."""
    at_hub = state.player in state.chamber.hub
    if state.phase is Phase.PREPARE and at_hub:
        return "record"
    if state.phase is Phase.RECORDING:
        return "save"
    if state.phase is Phase.COMMITTED and at_hub:
        return "launch"
    return None


def _echo(state: State) -> tuple[str, bool, str]:
    verb = echo_verb(state)
    if verb is not None:
        label = {
            "record": "Record",
            "save": "Save recording",
            "launch": "Launch echo",
        }[verb]
        return label, True, ""
    if state.phase is Phase.COMMITTED:
        return (
            "Return to hub to launch",
            False,
            "The echo can only launch from a hub tile; walk back to the hub",
        )
    if state.phase is Phase.REPLAY:
        return (
            "Echo running",
            False,
            "The echo is running; reach the elevator or retry from launch",
        )
    if state.phase is Phase.PREPARE:
        return "Record", False, "Recording can only start from a hub tile"
    return "Echo running", False, "This chamber is finished"


def stages_power(state: State) -> bool:
    """Whether console changes wait for Apply and cost a turn (recording, replay)."""
    return state.phase in {Phase.RECORDING, Phase.REPLAY}


def apply_label(state: State) -> str:
    return "Apply (costs 1 turn)" if stages_power(state) else "Done"


def _status(
    action_id: str,
    state: State,
    scope: str,
    undoable: bool,
    failure: str,
    reading: bool,
) -> tuple[str, bool, str]:
    label = LABELS.get((scope, action_id), BINDINGS[action_id].label)
    if action_id == "wait" and state.phase not in {Phase.RECORDING, Phase.REPLAY}:
        return label, False, "No turn to spend yet; record or launch the echo first"
    if (
        action_id in (*MOVE_IDS, "wait")
        and state.phase is Phase.RECORDING
        and len(state.recording) >= state.chamber.max_turns
    ):
        return label, False, resolve("Recording full; {key:echo} saves it")
    if action_id == "console" and reading:
        return "Read log", True, ""
    if action_id == "console" and state.player not in state.chamber.consoles:
        return label, False, "Stand on the hub console to change power"
    if action_id == "echo":
        return _echo(state)
    if action_id in ("preview_prev", "preview_next") and state.phase not in {
        Phase.COMMITTED,
        Phase.REPLAY,
    }:
        return label, False, "Save a recording first; then preview its turns"
    if scope == "console" and action_id == "apply":
        return apply_label(state), True, ""
    if action_id == "undo" and not undoable:
        return label, False, "Nothing to undo yet"
    if action_id == "retry":
        if scope == "failure" and failure != "replay":
            return label, False, "No launch to retry from; the take was discarded"
        if scope != "failure" and state.retry_snapshot is None:
            return label, False, "Launch the echo first; there is nothing to retry"
    if action_id == "rerecord" and state.phase is Phase.REPLAY:
        return (
            label,
            False,
            resolve(
                "The echo is running; {key:restart} clears the chamber for a new take"
            ),
        )
    if action_id == "rerecord" and state.phase not in {
        Phase.RECORDING,
        Phase.COMMITTED,
    }:
        return label, False, "There is no recording to discard"
    return label, True, ""


def available_actions(
    state: State,
    screen: str,
    modal: str | None,
    *,
    undoable: bool = False,
    failure: str = "",
    terminals: tuple[story.Terminal, ...] = (),
) -> list[Action]:
    """Actions for the current context, each enabled or disabled with a reason.

    `modal` is the active overlay in the game screen (console, pause, failure,
    guide, settings, lesson_choice, result) or None for plain gameplay.
    `failure` is "replay" or "recording" while the failure card is open.
    `terminals` are the chamber's log terminals: next to one (and not on the
    console), the console key reads its log instead.
    """
    scope = scope_for(screen, modal)
    reading = scope == "play" and story.in_reach(state, terminals) is not None
    actions = []
    for action_id in SCOPES[scope]:
        label, enabled, reason = _status(
            action_id, state, scope, undoable, failure, reading
        )
        binding = BINDINGS[action_id]
        actions.append(
            Action(
                action_id,
                cap(action_id, scope),
                label,
                enabled,
                reason,
                binding.short if label == binding.label else "",
            )
        )
    return actions


def find(actions: list[Action], action_id: str) -> Action:
    return next(action for action in actions if action.id == action_id)


def legend(actions: list[Action], ids: tuple[str, ...]) -> str:
    """One line of "Key Label" pairs for the enabled actions among `ids`."""
    by_id = {action.id: action for action in actions}
    return "  ".join(
        f"{by_id[i].key} {by_id[i].label}" if by_id[i].key else by_id[i].label
        for i in ids
        if i in by_id and by_id[i].enabled
    )


# ---- progressive disclosure ------------------------------------------------------
#
# Chambers introduce the bar buttons gradually. Only the bar and the guide's
# Controls page hide an action; its key keeps working. Chamber 1 already needs
# the console and the echo key: recording and launching start in the hub, so a
# chamber's own lesson never hides what it needs.

MOVE_IDS = ("move_up", "move_down", "move_left", "move_right")
ALWAYS_SHOWN = ("restart", "pause", "guide", "hint", "mute", "fullscreen")
BASE_SHOWN = ("wait", "undo")
INTRODUCED: dict[int, tuple[str, ...]] = {
    1: ("console", "echo"),
    3: ("retry", "rerecord", "preview_prev", "preview_next"),
}


def introduced(level: int) -> tuple[str, ...]:
    """Actions that first appear in this chamber (they get a one-time highlight)."""
    return INTRODUCED.get(level, ())


def shown_actions(level: int) -> frozenset[str]:
    """Gameplay actions the bar and the Controls page list in this chamber."""
    ids = set(MOVE_IDS) | set(ALWAYS_SHOWN) | set(BASE_SHOWN)
    for first, added in INTRODUCED.items():
        if first <= level:
            ids.update(added)
    return frozenset(ids)


# ---- text that names keys --------------------------------------------------------

PLACEHOLDER = re.compile(r"\{(key|label):([a-z_]+)\}")
DESCRIPTIONS = {
    "wait": "Wait one turn",
    "console": "Open the power console on the hub console, or read a log terminal on or next to you",
    "echo": "Record at the hub, save the recording, then launch the echo",
    "undo": "Undo the last move",
    "retry": "Run the echo again from launch",
    "restart": "Clear the chamber and start again",
    "rerecord": "Throw away the recording",
    "pause": "Pause menu, settings and chamber select",
    "guide": "Open or close this guide",
    "hint": "Reveal the next hint",
    "mute": "Mute or unmute",
    "fullscreen": "Toggle fullscreen",
}
PREVIEW_TEXT = "Preview the echo's later turns once a recording is saved"


def key_text(action_id: str) -> str:
    """How text names the key(s) of an action: "Enter", "D or Right", "WASD or ..."."""
    if action_id == "move":
        if pad_in_use():
            return "the D-pad"
        caps = "".join(
            BINDINGS[i].cap for i in ("move_up", "move_left", "move_down", "move_right")
        )
        return f"{caps} or the arrow keys"
    binding = BINDINGS[action_id]
    if action_id in MOVE_IDS and not (pad_in_use() and binding.pad):
        arrow = binding.keys[-1].removeprefix("KEY_").capitalize()
        return f"{binding.cap} or {arrow}"
    return cap(action_id)


def check_text(text: str) -> None:
    """Raise ValueError for an unknown placeholder or a stray brace."""
    for _, action_id in PLACEHOLDER.findall(text):
        if action_id not in BINDINGS and action_id != "move":
            raise ValueError(f"unknown action {action_id!r} in {text!r}")
    rest = PLACEHOLDER.sub("", text)
    if "{" in rest or "}" in rest:
        raise ValueError(f"malformed placeholder in {text!r}")


def resolve(text: str) -> str:
    """Fill `{key:echo}` and `{label:echo}` from the binding table."""
    check_text(text)
    return PLACEHOLDER.sub(
        lambda m: key_text(m[2]) if m[1] == "key" else BINDINGS[m[2]].label, text
    )


def controls_lines(level: int) -> list[str]:
    """The guide's Controls page: one "Key: what it does" line per shown action."""
    shown = shown_actions(level)
    lines = [f"{key_text('move')}: Move one tile"]
    for action_id in SCOPES["play"]:
        if action_id not in shown or action_id in MOVE_IDS:
            continue
        if action_id == "preview_prev":
            keys = f"{cap(action_id)} {cap('preview_next')}"
            lines.append(f"{keys}: {PREVIEW_TEXT}")
        elif action_id != "preview_next":
            lines.append(f"{cap(action_id) or 'Bar button'}: {DESCRIPTIONS[action_id]}")
    return lines
