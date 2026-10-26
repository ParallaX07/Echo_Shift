import json

import pytest

from tools import audition_music


@pytest.mark.parametrize(
    "text,expected",
    [("3", [3]), ("1-4", [1, 2, 3, 4]), ("1,4,7-8", [1, 4, 7, 8]), ("-3", [-3])],
)
def test_parse_range(text, expected):
    assert audition_music.parse_range(text) == expected


@pytest.mark.parametrize("text", ["5-2", "x", "0-9"])
def test_parse_range_rejects_bad_input(text):
    with pytest.raises(ValueError):
        audition_music.parse_range(text, 0, 7)


def test_sweep_size_and_order():
    found = audition_music.sweep([0, 1], [0, 3], [5, 6, 7], transp=-2)
    assert len(found) == 12
    assert found[0] == {"preset": 0, "transp": -2, "instr": 0, "seed": 5}
    assert found[1]["seed"] == 6
    assert found[3] == {"preset": 0, "transp": -2, "instr": 3, "seed": 5}
    assert found[6]["preset"] == 1


def entry(seed, **extra):
    return {"preset": 1, "transp": 0, "instr": 2, "seed": seed, **extra}


def test_merge_keeps_earlier_picks_and_skips_duplicates(tmp_path):
    path = tmp_path / "nested/candidates.json"
    audition_music.merge_kept(path, [entry(1, mml=["a"])])
    merged = audition_music.merge_kept(path, [entry(1, mml=["b"]), entry(2)])
    assert [item["seed"] for item in merged] == [1, 2]
    assert merged[0]["mml"] == ["a"]
    assert json.loads(path.read_text()) == merged
