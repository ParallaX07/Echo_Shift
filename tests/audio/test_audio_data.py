"""The baked audio data parses, loads with Sound.mml() and respects the channels."""

import json

import pytest
import pyxel

from echo_shift.paths import resource_path

REQUIRED_SFX = (
    "move",
    "wait",
    "reject",
    "power_on",
    "power_off",
    "over_budget",
    "record_start",
    "record_tick",
    "commit",
    "launch",
    "echo_expire",
    "pad_on",
    "pad_off",
    "gate_open",
    "gate_close",
    "elevator_start",
    "fail",
    "clear",
    "ui_hover",
    "ui_select",
    "dialogue",
    "undo",
    "pickup",
)
MUSIC_IDS = {"title", "play_calm", "play_replay", "clear_sting", "final"}
SOURCE_KEYS = {"preset", "transp", "instr", "seed", "pyxel_version"}


def read(name):
    return json.loads(resource_path("assets", "audio", name).read_text("utf-8"))


def loads(code):
    sound = pyxel.Sound()
    sound.mml(code)
    return sound


def music_problems(tracks):
    """Everything wrong with a music table, as readable strings."""
    problems = []
    for name, entry in tracks.items():
        codes = entry.get("mml")
        if name not in MUSIC_IDS:
            problems.append(f"{name}: unknown track id")
        if not isinstance(codes, list) or not 1 <= len(codes) <= 3:
            problems.append(f"{name}: music uses channels 0-2, so 1-3 mml strings")
            continue
        for code in codes:
            try:
                loads(code)
            except Exception as error:  # noqa: BLE001
                problems.append(f"{name}: {error}")
        if not isinstance(entry.get("loop"), bool):
            problems.append(f"{name}: loop must be true or false")
        source = entry.get("source")
        if not isinstance(source, dict) or not SOURCE_KEYS <= source.keys():
            problems.append(f"{name}: source must record {sorted(SOURCE_KEYS)}")
    return problems


def test_sfx_has_every_listed_effect_and_loads():
    sfx = read("sfx.json")
    assert set(REQUIRED_SFX) <= sfx.keys()
    for name, code in sfx.items():
        assert isinstance(code, str), name
        seconds = loads(code).total_sec()
        assert seconds is not None and 0 < seconds <= 1.1, name


def test_sfx_stay_short():
    sfx = read("sfx.json")
    long = {"fail", "clear"}
    for name, code in sfx.items():
        limit = 1.1 if name in long else 0.5
        assert loads(code).total_sec() <= limit, name


def test_music_entries_are_valid():
    assert music_problems(read("music.json")) == []


def test_clear_sting_does_not_loop():
    sting = read("music.json").get("clear_sting")
    assert sting is None or sting["loop"] is False


GOOD = {
    "mml": ["T100 L8 CDE", "T100 L8 EFG"],
    "loop": True,
    "source": {
        "preset": 0,
        "transp": 0,
        "instr": 0,
        "seed": 1,
        "pyxel_version": "2.9.9",
    },
}


@pytest.mark.parametrize(
    "change",
    [
        {"mml": ["C"] * 4},
        {"mml": []},
        {"mml": ["ZZZ("]},
        {"loop": "yes"},
        {"source": {"preset": 0}},
        {"source": None},
    ],
)
def test_music_check_rejects_bad_entries(change):
    assert music_problems({"title": {**GOOD, **change}})


def test_music_check_accepts_a_good_entry_and_rejects_unknown_ids():
    assert music_problems({"title": GOOD}) == []
    assert music_problems({"menu": GOOD})
