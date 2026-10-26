from tools import stage_build


def test_stage_build_copies_audio(tmp_path, monkeypatch):
    monkeypatch.setattr(stage_build, "DEST", tmp_path / "app")
    stage_build.main()
    staged = tmp_path / "app/assets/audio"
    assert (staged / "sfx.json").is_file() and (staged / "music.json").is_file()
