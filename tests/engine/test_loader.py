import copy
import json
from pathlib import Path

import pytest

from echo_shift.engine.loader import LevelError, from_dict, load
from echo_shift.engine.model import Position


@pytest.fixture
def example_data():
    return json.loads(
        (Path(__file__).parents[2] / "levels/fixtures/example_60.json").read_text()
    )


def test_loads_example_with_default_turn_limit(example_data):
    example_data.pop("max_turns")
    assert (
        load(Path(__file__).parents[2] / "levels/fixtures/example_60.json").max_turns
        == 12
    )
    assert from_dict(example_data).max_turns == 12


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d.pop("hub"), "missing chamber fields"),
        (lambda d: d.update(hub=[]), "hub"),
        (lambda d: d.update(consoles=[]), "console"),
        (lambda d: d.pop("start"), "missing chamber fields"),
        (lambda d: d.pop("exit"), "missing chamber fields"),
        (lambda d: d.update(start=[2, 1]), "start must be on a hub tile"),
        (lambda d: d["devices"][0].update(pad="missing"), "dangling"),
        (lambda d: d["devices"][0].update(circuit="missing"), "dangling"),
        (lambda d: d["circuits"][1].update(devices=["unknown"]), "unknown device"),
        (lambda d: d["circuits"][1].update(zones=["unknown"]), "unknown zone"),
        (
            lambda d: d["devices"].append(copy.deepcopy(d["devices"][0])),
            "duplicate device id",
        ),
        (
            lambda d: d["zones"].append(copy.deepcopy(d["zones"][0])),
            "duplicate zone id",
        ),
        (
            lambda d: d["circuits"].append(copy.deepcopy(d["circuits"][0])),
            "duplicate circuit id",
        ),
        (
            lambda d: d["pads"].append(copy.deepcopy(d["pads"][0])),
            "duplicate pad id",
        ),
        (lambda d: d["circuits"][0].update(load=61), "exceeds generator capacity"),
        (lambda d: d.update(max_turns=0), "max_turns"),
        (lambda d: d.update(max_turns=13), "max_turns"),
        (lambda d: d.update(max_turns=1.5), "max_turns"),
        (lambda d: d.update(max_turns=True), "max_turns"),
        (lambda d: d["pads"][0].update(timer=-1), "timer"),
        (lambda d: d.update(idea="speed"), "idea"),
        (lambda d: d.update(goals={"turns": 3}), "goals"),
        (lambda d: d.update(goals=[3, 0]), "goals"),
        (lambda d: d.update(goals={"turns": 3.5, "recorded": 0}), "integers"),
        (lambda d: d.update(goals={"turns": True, "recorded": 0}), "integers"),
        (lambda d: d.update(goals={"turns": 0, "recorded": 0}), "at least one turn"),
        (lambda d: d.update(goals={"turns": 3, "recorded": -1}), "no negative"),
        (lambda d: d.update(max_turns=2, goals={"turns": 9, "recorded": 3}), "exceeds"),
    ],
)
def test_rejects_invalid_chamber_fixtures(example_data, mutate, message):
    mutate(example_data)
    with pytest.raises(LevelError, match=message):
        from_dict(example_data)


def test_idea_and_goals_are_optional_and_read_when_present(example_data):
    plain = from_dict(example_data)
    assert plain.idea is None and plain.goals is None
    example_data.update(idea="timed_pads", goals={"turns": 7, "recorded": 2})
    chamber = from_dict(example_data)
    assert chamber.idea == "timed_pads"
    assert (chamber.goals.turns, chamber.goals.recorded) == (7, 2)


CELL = {"id": "cell-a", "position": [3, 1], "value": 15}
CONDUIT = {"id": "line-a", "circuit": "lab-lights", "tiles": [[3, 1], [4, 1]]}


def test_cells_and_conduits_are_optional_and_read_when_present(example_data):
    plain = from_dict(example_data)
    assert plain.cells == () and plain.conduits == ()
    example_data.update(cells=[CELL], conduits=[CONDUIT])
    chamber = from_dict(example_data)
    assert chamber.cells[0].value == 15
    assert chamber.cells[0].position == Position(3, 1)
    assert chamber.conduits[0].circuit_id == "lab-lights"
    assert chamber.conduits[0].tiles == (Position(3, 1), Position(4, 1))


def test_a_cell_can_make_a_heavy_circuit_possible(example_data):
    example_data["circuits"][0]["load"] = 70
    with pytest.raises(LevelError, match="exceeds generator capacity"):
        from_dict(example_data)
    example_data["cells"] = [CELL]
    assert from_dict(example_data).circuits[0].load == 70


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d.update(cells=[{**CELL, "value": 0}]), "positive integer"),
        (lambda d: d.update(cells=[{**CELL, "value": 1.5}]), "positive integer"),
        (lambda d: d.update(cells=[{**CELL, "value": True}]), "positive integer"),
        (lambda d: d.update(cells=[{**CELL, "position": [9, 9]}]), "outside"),
        (lambda d: d.update(cells=[{**CELL, "position": [0, 1]}]), "walkable"),
        (lambda d: d.update(cells=[{**CELL, "position": [4, 1]}]), "walkable"),
        (lambda d: d.update(cells=[{**CELL, "position": [1, 1]}]), "start tile"),
        (lambda d: d.update(cells=[CELL, dict(CELL)]), "duplicate cell id"),
        (lambda d: d.update(cells=[{**CELL, "id": "lab"}]), "duplicate ids"),
        (lambda d: d.update(cells=[{"id": "x", "position": [3, 1]}]), "invalid"),
        (lambda d: d.update(conduits=[{**CONDUIT, "circuit": "nope"}]), "circuit"),
        (lambda d: d.update(conduits=[{**CONDUIT, "tiles": [[9, 9]]}]), "outside"),
        (lambda d: d.update(conduits=[{**CONDUIT, "tiles": [[0, 1]]}]), "wall"),
        (lambda d: d.update(conduits=[{**CONDUIT, "tiles": [[1, 1]]}]), "hub"),
        (lambda d: d.update(conduits=[CONDUIT, dict(CONDUIT)]), "duplicate conduit"),
        (lambda d: d.update(conduits=[{**CONDUIT, "id": "lab"}]), "duplicate ids"),
    ],
)
def test_rejects_invalid_cells_and_conduits(example_data, mutate, message):
    mutate(example_data)
    with pytest.raises(LevelError, match=message):
        from_dict(example_data)
