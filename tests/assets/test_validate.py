import json

from PIL import Image

from tools import validate_assets


def test_validator_reports_each_asset_rule(tmp_path, monkeypatch):
    root = tmp_path
    (root / "assets/sprites").mkdir(parents=True)
    colors = [
        "#000000",
        "#1D2B53",
        "#7E2553",
        "#008751",
        "#AB5236",
        "#5F574F",
        "#C2C3C7",
        "#FFF1E8",
        "#FF004D",
        "#FFA300",
        "#FFEC27",
        "#00E436",
        "#29ADFF",
        "#83769C",
        "#FF77A8",
        "#FFCCAA",
    ]
    (root / "assets/palette.json").write_text(
        json.dumps(
            {
                "colors": [{"hex": c} for c in colors],
                "minimum_opaque_pixels": {"character": 576},
            }
        )
    )
    assets = [
        {"id": "missing", "type": "character", "status": "ok"},
        {"id": "wrong_size", "type": "character", "status": "missing"},
        {"id": "wrong_mode", "type": "character", "status": "missing"},
        {"id": "soft_alpha", "type": "character", "status": "missing"},
        {"id": "blank", "type": "character", "status": "missing"},
        {"id": "off_palette", "type": "character", "status": "missing"},
        {"id": "too_small", "type": "character", "status": "missing"},
        {"id": "echo_idle_0", "type": "character", "status": "missing"},
    ]
    (root / "assets/manifest.json").write_text(json.dumps({"assets": assets}))
    Image.new("RGBA", (16, 16), (255, 163, 0, 255)).save(
        root / "assets/sprites/wrong_size.png"
    )
    Image.new("RGB", (96, 96), "#FFA300").save(root / "assets/sprites/wrong_mode.png")
    Image.new("RGBA", (96, 96), (255, 163, 0, 128)).save(
        root / "assets/sprites/soft_alpha.png"
    )
    Image.new("RGBA", (96, 96), (0, 0, 0, 0)).save(root / "assets/sprites/blank.png")
    Image.new("RGBA", (96, 96), (123, 123, 123, 255)).save(
        root / "assets/sprites/off_palette.png"
    )
    small = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
    small.putpixel((0, 0), (255, 163, 0, 255))
    small.save(root / "assets/sprites/too_small.png")
    echo = Image.new("RGBA", (96, 96), (255, 163, 0, 255))
    echo.save(root / "assets/sprites/echo_idle_0.png")
    monkeypatch.setattr(validate_assets, "ROOT", root)

    errors = "\n".join(validate_assets.validate())
    for expected in (
        "approved sprite is missing",
        "expected 96x96 RGBA",
        "alpha must be binary",
        "sprite is blank",
        "outside the palette",
        "needs 576",
        "six-pixel margin and y=87 baseline",
        "echo outline colour",
    ):
        assert expected in errors
