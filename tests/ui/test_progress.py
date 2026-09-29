import json

from echo_shift.ui import progress


def test_progress_round_trip_and_corrupt_save(tmp_path, monkeypatch):
    monkeypatch.setattr(progress, "user_data_dir", lambda: tmp_path)
    assert progress.load_unlocked(3) == 1
    progress.save_unlocked(2)
    assert json.loads((tmp_path / "progress.json").read_text()) == {"unlocked": 2}
    assert progress.load_unlocked(3) == 2
    (tmp_path / "progress.json").write_text('{"unlocked": true}')
    assert progress.load_unlocked(3) == 1
    (tmp_path / "progress.json").write_text('{"unlocked": 99}')
    assert progress.load_unlocked(3) == 3
