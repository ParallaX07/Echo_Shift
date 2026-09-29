import json

from PIL import Image, ImageDraw

from tools import process_asset


def test_process_keys_magenta_snaps_palette_and_preserves_group_anchor(
    tmp_path, monkeypatch
):
    root = tmp_path
    for folder in ("assets/raw", "assets/sprites"):
        (root / folder).mkdir(parents=True)
    palette = [
        {"index": i, "hex": color, "role": "test"}
        for i, color in enumerate(
            (
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
            )
        )
    ]
    (root / "assets/palette.json").write_text(json.dumps({"colors": palette}))
    ids = ["frame_a", "frame_b", "tile"]
    manifest = {
        "assets": [
            {
                "id": name,
                "type": "tile" if name == "tile" else "character",
                "group": "tiles" if name == "tile" else "pair",
                "source": "key" if name == "tile" else "alpha",
            }
            for name in ids
        ]
    }
    (root / "assets/manifest.json").write_text(json.dumps(manifest))
    for name, box in (("frame_a", (5, 4, 17, 25)), ("frame_b", (7, 4, 19, 25))):
        image = Image.new("RGBA", (24, 28), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle(box, fill=(255, 163, 0, 255))
        image.putpixel((0, 0), (255, 163, 0, 1))
        image.putpixel((23, 27), (255, 163, 0, 1))
        image.save(root / "assets/raw" / f"{name}.png")
    tile = Image.new("RGB", (32, 32), "#FF00FF")
    ImageDraw.Draw(tile).rectangle((0, 0, 31, 31), fill="#FFA300")
    tile.save(root / "assets/raw/tile.png")
    monkeypatch.setattr(process_asset, "ROOT", root)

    outputs = [process_asset.process(name) for name in ids]
    first, second, keyed = (Image.open(path).convert("RGBA") for path in outputs)
    assert first.size == second.size == keyed.size == (96, 96)
    assert first.getchannel("A").getextrema() == (0, 255)
    assert set(first.get_flattened_data()) <= {(0, 0, 0, 0), (255, 163, 0, 255)}
    assert first.getchannel("A").getbbox() == second.getchannel("A").getbbox()
    bounds = first.getchannel("A").getbbox()
    assert bounds[0] >= 6 and bounds[1] >= 6 and bounds[2] <= 90
    assert abs((bounds[2] - bounds[0]) / (bounds[3] - bounds[1]) - 13 / 22) < 0.05
    assert bounds[3] == 87
    assert keyed.getpixel((0, 0))[3] == 255
