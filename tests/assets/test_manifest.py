import json

from PIL import Image

from tools import validate_assets


def test_every_approved_asset_has_a_sprite_and_atlas_entry(tmp_path, monkeypatch):
    root = tmp_path
    (root / "assets/sprites").mkdir(parents=True)
    (root / "assets/atlas.json").write_text(json.dumps({"one": {"bank": 0}}))
    (root / "assets/manifest.json").write_text(
        json.dumps(
            {"assets": [{"id": "one", "status": "ok"}, {"id": "two", "status": "ok"}]}
        )
    )
    Image.new("RGBA", (96, 96), (255, 163, 0, 255)).save(
        root / "assets/sprites/one.png"
    )
    monkeypatch.setattr(validate_assets, "ROOT", root)
    assert validate_assets.validate_manifest() == [
        "two: approved asset needs both sprite and atlas entry"
    ]
