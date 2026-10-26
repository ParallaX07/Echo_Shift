import json

import pytest

from echo_shift.ui import progress


@pytest.fixture
def save(tmp_path):
    def write(text):
        (tmp_path / "progress.json").write_text(text)
        return progress.load(3, tmp_path)

    return write


def test_missing_save_gives_defaults(tmp_path):
    assert progress.load(3, tmp_path) == progress.Progress()
    defaults = progress.Progress()
    assert defaults.version == 2 and defaults.unlocked == 1 and defaults.goals == {}
    assert defaults.settings == progress.Settings(7, 7, False, False, False)


def test_round_trip_keeps_everything_and_writes_the_version(tmp_path):
    saved = progress.Progress(
        unlocked=3,
        goals={"1": {"turns": True, "recorded": False}},
        settings=progress.Settings(3, 0, True, True, True),
    )
    progress.save(saved, tmp_path)
    assert json.loads((tmp_path / "progress.json").read_text()) == {
        "unlocked": 3,
        "goals": {"1": {"turns": True, "recorded": False}},
        "settings": {
            "music_volume": 3,
            "sfx_volume": 0,
            "mute": True,
            "reduced_motion": True,
            "crt": True,
        },
        "version": 2,
    }
    assert progress.load(3, tmp_path) == saved


def test_save_creates_the_directory_and_leaves_no_temp_file(tmp_path):
    target = tmp_path / "nested" / "data"
    progress.save(progress.Progress(unlocked=2), target)
    assert [p.name for p in target.iterdir()] == ["progress.json"]
    progress.save(progress.Progress(unlocked=3), target)
    assert progress.load(3, target).unlocked == 3
    assert [p.name for p in target.iterdir()] == ["progress.json"]


def test_failed_write_keeps_the_old_save_and_cleans_up(tmp_path, monkeypatch):
    progress.save(progress.Progress(unlocked=2), tmp_path)

    def boom(*args):
        raise OSError("disk full")

    monkeypatch.setattr(progress.os, "replace", boom)
    with pytest.raises(OSError):
        progress.save(progress.Progress(unlocked=3), tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == ["progress.json"]
    assert progress.load(3, tmp_path).unlocked == 2


def test_old_format_save_keeps_unlocks_and_defaults_the_rest(save):
    loaded = save('{"unlocked": 2}')
    assert loaded.unlocked == 2
    assert loaded.goals == {} and loaded.settings == progress.Settings()
    assert loaded.version == 2


@pytest.mark.parametrize("text", ["", "{", "not json", "[]", "null", "7", '"x"'])
def test_corrupt_or_wrong_shaped_files_load_defaults(save, text):
    assert save(text) == progress.Progress()


@pytest.mark.parametrize(
    "unlocked,expected",
    [(99, 3), (0, 1), (-4, 1), (True, 1), ("2", 1), (2.5, 1), (None, 1), (3, 3)],
)
def test_unlocked_is_validated_and_clamped(save, unlocked, expected):
    assert save(json.dumps({"unlocked": unlocked})).unlocked == expected


def test_partly_corrupt_save_never_wipes_valid_unlocks(save):
    loaded = save(
        json.dumps({"unlocked": 2, "goals": [1], "settings": "loud", "version": "x"})
    )
    assert loaded.unlocked == 2
    assert loaded.goals == {} and loaded.settings == progress.Settings()


def test_each_settings_field_is_validated_on_its_own(save):
    loaded = save(
        json.dumps(
            {
                "unlocked": 2,
                "settings": {
                    "music_volume": 9,
                    "sfx_volume": 4,
                    "mute": "yes",
                    "reduced_motion": True,
                    "crt": 1,
                },
            }
        )
    )
    assert loaded.settings == progress.Settings(7, 4, False, True, False)
    loaded = save(
        json.dumps({"settings": {"music_volume": -1, "sfx_volume": True, "mute": True}})
    )
    assert loaded.settings == progress.Settings(7, 7, True, False, False)


def test_each_goal_entry_is_validated_on_its_own(save):
    loaded = save(
        json.dumps(
            {
                "goals": {
                    "1": {"turns": True, "recorded": True},
                    "2": {"turns": 1},
                    "x": {"turns": True},
                    "0": {"turns": True},
                    "3": "done",
                    "²": {"turns": True},
                }
            }
        )
    )
    assert loaded.goals == {
        "1": {"turns": True, "recorded": True},
        "2": {"turns": False, "recorded": False},
    }


def test_mute_round_trips_through_the_app_settings(player):
    game = player.game
    assert not game.muted
    player.press("M")
    assert game.muted
    assert progress.load(3, player.directory).settings.mute
    player.press("M")
    assert not progress.load(3, player.directory).settings.mute


def test_unlocking_keeps_goals_and_settings(player):
    progress.save(
        progress.Progress(
            goals={"1": {"turns": True, "recorded": True}},
            settings=progress.Settings(2, 5, True, False, True),
        ),
        player.directory,
    )
    from echo_shift.ui import app

    reloaded = app.Game()
    assert reloaded.muted
    reloaded.level = 1
    reloaded.unlock_next()
    saved = progress.load(3, player.directory)
    assert saved.unlocked == 2
    assert saved.goals == {"1": {"turns": True, "recorded": True}}
    assert saved.settings == progress.Settings(2, 5, True, False, True)


def test_record_goals_notes_a_clear_and_only_ever_upgrades():
    state = progress.Progress()
    assert not progress.cleared(state, 1)
    assert progress.record_goals(state, 1, turns=False, recorded=False) is True
    assert progress.cleared(state, 1)  # a goals entry means the chamber was cleared
    assert state.goals["1"] == {"turns": False, "recorded": False}
    assert progress.record_goals(state, 1, turns=True, recorded=False) is True
    assert progress.record_goals(state, 1, turns=False, recorded=True) is True
    assert state.goals["1"] == {"turns": True, "recorded": True}
    assert progress.record_goals(state, 1, turns=False, recorded=False) is False
    assert state.goals["1"] == {"turns": True, "recorded": True}


def test_goals_do_not_change_what_is_unlocked(tmp_path):
    state = progress.Progress(unlocked=1)
    progress.record_goals(state, 1, turns=True, recorded=True)
    assert state.unlocked == 1
    progress.save(state, tmp_path)
    assert progress.load(3, tmp_path).unlocked == 1
    assert progress.cleared(progress.Progress(unlocked=3), 2)
