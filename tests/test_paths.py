from pathlib import Path

from echo_shift import paths


def test_resource_path_is_relative_to_main() -> None:
    assert paths.resource_path("levels", "spike.json").is_file()


def test_user_data_dir_uses_xdg_and_creates_it(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    result = paths.user_data_dir()

    assert result == tmp_path / "echo-shift"
    assert result.is_dir()


def test_user_data_dir_uses_appdata_on_windows(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert paths.user_data_dir() == tmp_path / "EchoShift"
