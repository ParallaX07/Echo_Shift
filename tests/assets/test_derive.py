import json
from pathlib import Path

import pytest
from PIL import Image

from tools import derive_frames, validate_assets

ROOT = Path(__file__).resolve().parents[2]


def tiny():
    image = Image.new("RGBA", (4, 4))
    image.putpixel((0, 0), (255, 163, 0, 255))
    image.putpixel((1, 0), (255, 0, 77, 255))
    return image


@pytest.mark.parametrize(
    "angle,corner",
    [(90, (3, 0)), (180, (3, 3)), (270, (0, 3))],
)
def test_rotate_turns_clockwise(angle, corner):
    rotated = derive_frames.rotate(tiny(), angle)
    assert rotated.getpixel(corner) == (255, 163, 0, 255)
    assert sum(1 for pixel in rotated.get_flattened_data() if pixel[3]) == 2


def test_rotate_region_leaves_the_rest_alone():
    image = tiny()
    image.putpixel((3, 3), (0, 228, 54, 255))
    rotated = derive_frames.rotate(image, 90, [0, 0, 2])
    assert rotated.getpixel((1, 0)) == (255, 163, 0, 255)
    assert rotated.getpixel((3, 3)) == (0, 228, 54, 255)
    assert derive_frames.copy(image).tobytes() == image.tobytes()


@pytest.mark.parametrize("angle,box", [(45, None), (90, [3, 3, 4]), (90, [0, 0, 0])])
def test_rotate_rejects_bad_arguments(angle, box):
    with pytest.raises(ValueError):
        derive_frames.rotate(tiny(), angle, box)


def test_derived_sprites_are_deterministic_and_match_their_files():
    assets = [
        asset
        for asset in json.loads((ROOT / "assets/manifest.json").read_text())["assets"]
        if asset.get("source") == "derived"
    ]
    assert {asset["id"] for asset in assets} >= {
        "slot_up",
        "slot_right",
        "slot_down",
        "slot_left",
    }
    for asset in assets:
        first, second = derive_frames.derive(asset), derive_frames.derive(asset)
        assert first.tobytes() == second.tobytes()
        stored = Image.open(ROOT / "assets/sprites" / f"{asset['id']}.png")
        assert stored.convert("RGBA").tobytes() == first.tobytes()


def test_validator_checks_derived_entries(tmp_path, monkeypatch):
    (tmp_path / "assets/sprites").mkdir(parents=True)
    (tmp_path / "assets/atlas.json").write_text(
        json.dumps({"base": {}, "child": {}, "orphan": {}, "bare": {}})
    )
    assets = [
        {"id": "base", "status": "ok"},
        {
            "id": "child",
            "status": "ok",
            "source": "derived",
            "from": "base",
            "op": "copy",
        },
        {
            "id": "orphan",
            "status": "ok",
            "source": "derived",
            "from": "gone",
            "op": "copy",
        },
        {"id": "bare", "status": "ok", "source": "derived"},
    ]
    for asset in assets:
        Image.new("RGBA", (96, 96)).save(tmp_path / f"assets/sprites/{asset['id']}.png")
    (tmp_path / "assets/manifest.json").write_text(json.dumps({"assets": assets}))
    monkeypatch.setattr(validate_assets, "ROOT", tmp_path)
    assert validate_assets.validate_manifest() == [
        "orphan: parent gone is not approved",
        "bare: derived asset needs `from` and `op`",
    ]
