"""Panel lines that know how they want to be drawn.

Each kind is still the plain string it reads as, so text checks, wrapping
fallbacks and logs keep working; the card painter looks at `kind` and the
fields to draw key caps, check boxes, meters and badges instead of raw text.
"""


class Line(str):
    kind = "text"

    def __new__(cls, text: str, **fields):
        line = super().__new__(cls, text)
        line.__dict__.update(fields)
        return line


class Menu(Line):
    """A choosable row: key cap, label, a setting's value and, when disabled,
    the reason."""

    kind = "menu"
    key: str
    label: str
    note: str
    selected: bool
    enabled: bool
    value: str


def menu(
    key: str,
    label: str,
    note: str,
    selected: bool,
    enabled: bool,
    value: str = "",
    text: str | None = None,
) -> Menu:
    """`text` replaces how the row reads when it has its own wording."""
    if text is None:
        marker = ">" if selected else " "
        cap = f"{key} " if key else ""
        tail = f": {value}" if value else f" - {note}" if note else ""
        text = f"{marker} {cap}{label}{tail}"
    return Menu(
        text,
        key=key,
        label=label,
        note=note,
        selected=selected,
        enabled=enabled,
        value=value,
    )


class Tabs(Line):
    """Page names in a row, the current one lit."""

    kind = "tabs"
    names: tuple[str, ...]
    current: int


def tabs(names: list[str], current: int) -> Tabs:
    text = " ".join(f"[{n}]" if i == current else n for i, n in enumerate(names))
    return Tabs(text, names=tuple(names), current=current)


class Choice(Line):
    """A large option card: a heading and a sentence under it."""

    kind = "choice"
    head: str
    body: str
    key: str


def choice(head: str, body: str, key: str = "") -> Choice:
    return Choice(f"{head}: {body}", head=head, body=body, key=key)


class Check(Line):
    """A circuit row: a check box, its name and its load."""

    kind = "check"
    name: str
    amount: str
    checked: bool
    selected: bool
    target: bool


def check(name: str, load: int, checked: bool, selected: bool, target: bool) -> Check:
    amount = f"{load} UNIT{'' if load == 1 else 'S'}"
    return Check(
        f"{'>' if selected else ' '} {'*' if target else ' '} "
        f"[{'X' if checked else ' '}] {name}  {amount}",
        name=name,
        amount=amount,
        checked=checked,
        selected=selected,
        target=target,
    )


class Stat(Line):
    """A label and its value; `met` adds a MET / NOT MET badge."""

    kind = "stat"
    label: str
    value: str
    goal: str
    met: bool | None
    tone: str


def stat(
    label: str,
    value: object,
    goal: object = None,
    met: bool | None = None,
    tone: str = "plain",
) -> Stat:
    text = f"{label}: {value}"
    if goal is not None:
        text += f" / GOAL {goal} " + ("MET" if met else "NOT MET")
    return Stat(
        text,
        label=label,
        value=str(value),
        goal="" if goal is None else f"GOAL {goal}",
        met=met,
        tone=tone,
    )


class Meter(Line):
    """A load against a limit, drawn as a bar under the numbers."""

    kind = "meter"
    label: str
    used: int
    total: int


def meter(label: str, used: int, total: int) -> Meter:
    return Meter(f"{label} {used}/{total}", label=label, used=used, total=total)


class Keys(Line):
    """A row of key caps with their labels."""

    kind = "keys"
    pairs: tuple[tuple[str, str], ...]


def keys(pairs: list[tuple[str, str]]) -> Keys:
    """Reads as the upper-case legend; the caps keep the labels' own case."""
    text = "  ".join(f"{key} {label}" if key else label for key, label in pairs)
    return Keys(text.upper(), pairs=tuple(pairs))


class Callout(Line):
    """A boxed instruction with a small heading, like the lesson step."""

    kind = "callout"
    head: str
    body: str


def callout(head: str, body: str) -> Callout:
    return Callout(f"{head}: {body}", head=head, body=body)
