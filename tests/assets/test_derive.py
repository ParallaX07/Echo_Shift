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


AMBER, NAVY, GREEN, BLUE = (255, 163, 0), (29, 43, 83), (0, 228, 54), (41, 173, 255)
CLEAR = (0, 0, 0, 0)


def figure():
    """A 20 x 40 two-colour figure standing on the feet baseline (rows 47-86)."""
    image = Image.new("RGBA", (96, 96))
    for y in range(47, 87):
        for x in range(30, 50):
            image.putpixel((x, y), (*(AMBER if (x // 10 + y) % 2 else NAVY), 255))
    return image


def colours(image):
    return {pixel[:3] for pixel in image.get_flattened_data() if pixel[3]}


def opaque(image):
    return {
        (x, y)
        for y in range(image.height)
        for x in range(image.width)
        if image.getpixel((x, y))[3]
    }


def check_frame(image, parent, extra=()):
    assert image.size == (96, 96) and image.mode == "RGBA"
    assert {pixel[3] for pixel in image.get_flattened_data()} <= {0, 255}
    assert colours(image) <= colours(parent) | set(extra)


def test_offset_shifts_and_clips_at_the_frame():
    image = figure()
    moved = derive_frames.offset(image, 3, -2)
    check_frame(moved, image)
    assert opaque(moved) == {(x + 3, y - 2) for x, y in opaque(image)}
    assert derive_frames.offset(image, 55, 0).getchannel("A").getbbox()[2] == 96
    assert derive_frames.offset(image, 0, 0).tobytes() == image.tobytes()


@pytest.mark.parametrize("rows", [1, 4, -3])
def test_squash_keeps_the_feet_and_changes_the_height(rows):
    image = figure()
    squashed = derive_frames.squash(image, rows)
    check_frame(squashed, image)
    left, top, right, bottom = squashed.getchannel("A").getbbox()
    assert (left, right, bottom) == (30, 50, 87)
    assert top == 47 + rows
    assert squashed.getpixel((40, 86)) == image.getpixel((40, 86))


def test_squash_without_rows_is_identity_and_rejects_nonsense():
    image = figure()
    assert derive_frames.squash(image, 0).tobytes() == image.tobytes()
    with pytest.raises(ValueError):
        derive_frames.squash(image, 40)
    with pytest.raises(ValueError):
        derive_frames.squash(image, -50)


def test_palette_swap_maps_indices_and_leaves_other_colours():
    image = figure()
    for spec in ({"9": 11}, {9: 11}, [[9, 11]]):
        swapped = derive_frames.palette_swap(image, spec)
        check_frame(swapped, image, extra={GREEN})
        assert colours(swapped) == {NAVY, GREEN}
        assert opaque(swapped) == opaque(image)
    both = derive_frames.palette_swap(image, {"9": 1, "1": 9})
    assert colours(both) == {AMBER, NAVY}
    assert both.getpixel((40, 86)) != image.getpixel((40, 86))
    assert derive_frames.palette_swap(image, {"11": 12}).tobytes() == image.tobytes()


@pytest.mark.parametrize("spec", [{"9": 0}, {"9": 16}, {"9": True}, [[9, -1]]])
def test_palette_swap_never_draws_index_zero(spec):
    with pytest.raises(ValueError):
        derive_frames.palette_swap(figure(), spec)


def test_dissolve_hash_is_pinned_so_it_matches_on_every_platform():
    mixed = [derive_frames.mix(*args) for args in ((1, 2, 3), (0, 0, 0), (31, 31, 11))]
    assert mixed == [2151121503, 0, 2512316806]


def test_dissolve_removes_the_asked_fraction_in_a_stable_pattern():
    image = figure()
    total = len(opaque(image))
    previous = opaque(image)
    for step in range(11):
        frame = derive_frames.dissolve(image, step, 10, seed=5)
        check_frame(frame, image)
        assert frame.tobytes() == derive_frames.dissolve(image, step, 10, 5).tobytes()
        kept = opaque(frame)
        assert kept <= previous
        removed = total - len(kept)
        assert min(total * step / 10, total - 20) <= removed < total * step / 10 + 9
        assert {(x, 86) for x in range(30, 50)} <= kept
        previous = kept
    assert opaque(derive_frames.dissolve(image, 0, 10)) == opaque(image)
    assert opaque(derive_frames.dissolve(image, 10, 10)) == {
        (x, 86) for x in range(30, 50)
    }
    assert (
        derive_frames.dissolve(image, 5, 10, seed=1).tobytes()
        != derive_frames.dissolve(image, 5, 10, seed=2).tobytes()
    )


@pytest.mark.parametrize("args", [(11, 10), (-1, 10), (0, 0)])
def test_dissolve_rejects_bad_steps(args):
    with pytest.raises(ValueError):
        derive_frames.dissolve(figure(), *args)


def test_slide_moves_a_box_and_leaves_transparency_behind():
    image = figure()
    moves = [{"box": [30, 50, 10, 10], "dx": -5, "dy": 2}]
    slid = derive_frames.slide(image, moves)
    check_frame(slid, image)
    assert slid.getpixel((38, 50)) == CLEAR
    assert slid.getpixel((26, 54))[3] == 255
    assert slid.getpixel((26, 54)) == image.getpixel((31, 52))
    assert slid.getpixel((45, 55)) == image.getpixel((45, 55))


def test_slide_behind_keeps_what_is_already_there():
    image = figure()
    moves = [{"box": [40, 60, 10, 10], "dx": -15, "dy": 0}]
    in_front = derive_frames.slide(image, moves)
    behind = derive_frames.slide(image, moves, behind=True)
    assert in_front.getpixel((26, 62)) == image.getpixel((41, 62))
    assert in_front.getpixel((30, 62)) == image.getpixel((45, 62))
    assert image.getpixel((30, 62)) != image.getpixel((45, 62))
    assert behind.getpixel((30, 62)) == image.getpixel((30, 62))
    assert behind.getpixel((26, 62)) == image.getpixel((41, 62))
    assert opaque(behind) == opaque(in_front)


def test_slide_rejects_boxes_outside_the_image():
    with pytest.raises(ValueError):
        derive_frames.slide(figure(), [{"box": [90, 90, 10, 10], "dx": 0, "dy": 0}])


def test_ring_outlines_the_silhouette_outside_only():
    image = figure()
    ringed = derive_frames.ring(image, 11)
    check_frame(ringed, image, extra={GREEN})
    new = opaque(ringed) - opaque(image)
    assert new and all(ringed.getpixel(p)[:3] == GREEN for p in new)
    assert opaque(image) <= opaque(ringed)
    assert (29, 60) in new and (28, 60) not in new and (40, 46) in new
    assert (40, 87) not in new and (29, 87) not in new
    assert ringed.getchannel("A").getbbox() == (29, 46, 51, 87)


def test_ring_stays_inside_margin_and_above_the_feet():
    image = Image.new("RGBA", (96, 96))
    for x in range(6, 90):
        image.putpixel((x, 6), (*NAVY, 255))
        image.putpixel((x, 86), (*NAVY, 255))
    ringed = derive_frames.ring(image, 12)
    left, top, right, bottom = ringed.getchannel("A").getbbox()
    assert (left, top, right, bottom) == (6, 6, 90, 87)
    assert ringed.getpixel((40, 85)) == (*BLUE, 255)
    assert ringed.getpixel((40, 87)) == CLEAR


def test_ring_rejects_index_zero():
    with pytest.raises(ValueError):
        derive_frames.ring(figure(), 0)


NEW_FRAMES = {
    "player_step_0",
    "player_step_1",
    "echo_step_0",
    "echo_step_1",
    "echo_spawn_0",
    "echo_spawn_1",
    "echo_spawn_2",
    "echo_expire_0",
    "echo_expire_1",
    "echo_expire_2",
    "gate_mid",
    "pad_press",
    "pad_timed_glow_0",
    "pad_timed_glow_1",
    "pad_timed_glow_2",
    "elevator_on_1",
    "console_1",
}


def test_derived_frames_keep_format_palette_and_anchor_of_their_parents():
    assets = {
        asset["id"]: asset
        for asset in json.loads((ROOT / "assets/manifest.json").read_text())["assets"]
    }
    atlas = json.loads((ROOT / "assets/atlas.json").read_text())
    assert NEW_FRAMES <= {i for i, a in assets.items() if a.get("source") == "derived"}
    assert NEW_FRAMES <= set(atlas)
    for name in NEW_FRAMES:
        asset = assets[name]
        assert {"type", "group", "description", "from", "op", "params"} <= set(asset)
        assert asset["op"] in derive_frames.OPS
        sprite = Image.open(ROOT / "assets/sprites" / f"{name}.png").convert("RGBA")
        parent = Image.open(ROOT / "assets/sprites" / f"{asset['from']}.png").convert(
            "RGBA"
        )
        params = asset["params"]
        extra = set()
        if asset["op"] == "palette_swap":
            extra = {derive_frames.colour(int(i))[:3] for i in params["map"].values()}
        if asset["op"] == "ring":
            extra = {derive_frames.colour(params["index"])[:3]}
        check_frame(sprite, parent, extra)
        assert sprite.getchannel("A").getbbox()[3] == 87
        assert (
            sprite.getchannel("A").getbbox()[3] == parent.getchannel("A").getbbox()[3]
        )
        if asset["op"] == "palette_swap":
            assert opaque(sprite) == opaque(parent)
        if asset["op"] in ("dissolve", "ring"):
            assert (opaque(sprite) <= opaque(parent)) is (asset["op"] == "dissolve")


def test_stored_sprites_pass_the_asset_validator():
    assert validate_assets.validate() == []
    assert validate_assets.validate_manifest() == []


def test_stamp_paints_a_scaled_map_over_the_parent_or_a_cleared_one():
    parent = Image.new("RGBA", (6, 6), (255, 204, 170, 255))
    rows, legend = ["A.", ".B"], {"A": 8, "B": 10}
    over = derive_frames.stamp(parent, rows, legend, scale=2, x=1, y=1)
    assert over.getpixel((1, 1)) == (255, 0, 77, 255)
    assert over.getpixel((2, 2)) == (255, 0, 77, 255)
    assert over.getpixel((3, 1)) == (255, 204, 170, 255)  # '.' keeps the parent
    assert over.getpixel((3, 3)) == (255, 236, 39, 255)
    bare = derive_frames.stamp(parent, rows, legend, scale=2, clear=True)
    assert bare.getpixel((2, 0)) == (0, 0, 0, 0)
    assert bare.getpixel((0, 0)) == (255, 0, 77, 255)
    assert parent.getpixel((1, 1)) == (255, 204, 170, 255)


@pytest.mark.parametrize(
    "rows,legend,scale",
    [
        (["A", "AA"], {"A": 8}, 1),  # ragged
        (["AAAA"], {"A": 8}, 2),  # wider than the image
        (["A"], {"A": 0}, 1),  # index 0 is never drawn
        (["A"], {"A": 8}, 0),
    ],
)
def test_stamp_rejects_bad_maps(rows, legend, scale):
    with pytest.raises(ValueError):
        derive_frames.stamp(Image.new("RGBA", (6, 6)), rows, legend, scale=scale)


def test_the_cell_and_conduit_sprites_are_stamped_and_keep_the_floor_look():
    assets = {
        asset["id"]: asset
        for asset in json.loads((ROOT / "assets/manifest.json").read_text())["assets"]
    }
    for sprite in ("cell", "conduit_off", "conduit_live"):
        assert assets[sprite]["source"] == "derived" and assets[sprite]["op"] == "stamp"
    assert validate_assets.validate() == []
    cell = Image.open(ROOT / "assets/sprites/cell.png")
    assert cell.getchannel("A").getbbox()[3] == 87  # stands on the feet baseline
    floor = Image.open(ROOT / "assets/sprites/floor_lit.png").convert("RGBA")
    off = Image.open(ROOT / "assets/sprites/conduit_off.png").convert("RGBA")
    assert off.getpixel((0, 0)) == floor.getpixel((0, 0))  # a floor margin remains
    assert off.getchannel("A").getextrema() == (255, 255)
