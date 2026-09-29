"""JSON chamber loading and validation."""

import json
from pathlib import Path
from typing import Any

from .model import Chamber, Circuit, Device, Pad, Position, TileType, Zone


class LevelError(ValueError):
    """A chamber file is malformed or violates the level contract."""


def _position(value: Any, name: str) -> Position:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(not isinstance(part, int) or isinstance(part, bool) for part in value)
    ):
        raise LevelError(f"{name} must be a [x, y] integer position")
    return Position(*value)


def load(path: str | Path) -> Chamber:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LevelError(f"cannot read chamber: {exc}") from exc
    return from_dict(data)


def from_dict(data: Any) -> Chamber:
    if not isinstance(data, dict):
        raise LevelError("chamber must be a JSON object")
    required = {
        "grid",
        "hub",
        "consoles",
        "start",
        "exit",
        "capacity",
        "zones",
        "circuits",
        "pads",
        "devices",
    }
    missing = required - data.keys()
    if missing:
        raise LevelError(f"missing chamber fields: {', '.join(sorted(missing))}")
    try:
        grid = tuple(tuple(TileType(tile) for tile in row) for row in data["grid"])
        hub = frozenset(_position(value, "hub tile") for value in data["hub"])
        consoles = frozenset(_position(value, "console") for value in data["consoles"])
        start = _position(data["start"], "start")
        exit_position = _position(data["exit"], "exit")
        zones = tuple(
            Zone(
                item["id"], tuple(_position(pos, "zone tile") for pos in item["tiles"])
            )
            for item in data["zones"]
        )
        circuits = tuple(
            Circuit(
                item["id"],
                item["load"],
                tuple(item.get("zones", ())),
                tuple(item.get("devices", ())),
            )
            for item in data["circuits"]
        )
        pads = tuple(
            Pad(
                item["id"],
                _position(item["position"], "pad position"),
                item.get("timer", 3),
            )
            for item in data["pads"]
        )
        devices = tuple(
            Device(
                item["id"],
                TileType(item["kind"]),
                _position(item["position"], "device position"),
                item["circuit"],
                item["pad"],
            )
            for item in data["devices"]
        )
        capacity = data["capacity"]
        max_turns = data.get("max_turns", 12)
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, LevelError):
            raise
        raise LevelError(f"invalid chamber data: {exc}") from exc

    if not grid or any(not isinstance(row, (list, tuple)) for row in data["grid"]):
        raise LevelError("grid must be a non-empty rectangle")
    if not hub:
        raise LevelError("chamber must contain a hub")
    if not consoles:
        raise LevelError("chamber must contain a console")
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 0:
        raise LevelError("capacity must be a non-negative integer")
    if (
        not isinstance(max_turns, int)
        or isinstance(max_turns, bool)
        or not 1 <= max_turns <= 12
    ):
        raise LevelError("max_turns must be an integer from 1 to 12")
    for pad in pads:
        if (
            not isinstance(pad.timer_length, int)
            or isinstance(pad.timer_length, bool)
            or pad.timer_length < 0
        ):
            raise LevelError(f"pad {pad.id} timer must be a non-negative integer")
    try:
        chamber = Chamber(
            grid,
            start,
            hub,
            consoles,
            capacity,
            zones,
            circuits,
            pads,
            devices,
            exit_position,
            max_turns,
        )
    except ValueError as exc:
        raise LevelError(str(exc)) from exc
    if start not in hub:
        raise LevelError("start must be on a hub tile")
    if not consoles <= hub:
        raise LevelError("console must be inside the hub")
    if any(
        chamber.tile_at(position) not in {TileType.HUB, TileType.CONSOLE}
        for position in hub
    ):
        raise LevelError("hub positions must be hub or console tiles")
    if any(chamber.tile_at(pad.position) is not TileType.PAD for pad in pads):
        raise LevelError("pad position must be a pad tile")
    if any(chamber.tile_at(device.position) is not device.kind for device in devices):
        raise LevelError("device tile must match its kind")
    if chamber.tile_at(exit_position) is not TileType.ELEVATOR:
        raise LevelError("exit must be an elevator tile")
    if not any(
        device.kind is TileType.ELEVATOR and device.position == exit_position
        for device in devices
    ):
        raise LevelError("exit must link to an elevator device")
    identifiers = [
        item.id for group in (zones, circuits, pads, devices) for item in group
    ]
    if len(identifiers) != len(set(identifiers)):
        raise LevelError("duplicate ids across chamber entities")
    total = sum(circuit.load for circuit in circuits)
    if any(circuit.load > capacity for circuit in circuits):
        raise LevelError("single circuit load exceeds generator capacity")
    if total < 0:
        raise LevelError("circuit loads must be non-negative")
    return chamber
