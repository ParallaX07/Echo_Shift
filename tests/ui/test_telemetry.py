"""Playtest records count undos, refused keys, failure choices and previews."""

import json

from echo_shift.ui import telemetry


def last_record(directory):
    return json.loads((directory / "playtest.jsonl").read_text().splitlines()[-1])


def test_attempt_counters_are_written_to_the_record(tmp_path):
    attempt = telemetry.Attempt(2, path=tmp_path / "log.jsonl")
    attempt.undos += 2
    attempt.record_disabled("echo")
    attempt.record_disabled("echo")
    attempt.record_disabled("undo")
    attempt.record_failure_choice("retry")
    attempt.record_failure_choice("undo")
    attempt.record_preview(3)
    attempt.record_preview(5)
    attempt.finish(False)
    record = json.loads((tmp_path / "log.jsonl").read_text())
    assert record["undos"] == 2
    assert record["disabled_presses"] == {"echo": 2, "undo": 1}
    assert record["failure_choices"] == {"retry": 1, "undo": 1}
    assert record["previews"] == [3, 5]


def test_new_attempt_starts_with_empty_counters(tmp_path):
    record = telemetry.Attempt(1, path=tmp_path / "log.jsonl")
    assert (record.undos, record.disabled_presses) == (0, {})
    assert (record.failure_choices, record.previews) == ({}, [])


def test_app_counts_undos_refused_keys_and_failure_choices(player):
    game = player.game
    game.open_level(2)
    player.press("F")
    player.press("Z")  # nothing to undo
    player.press("SPACE")  # no turn to wait yet
    player.press("R")  # nothing to retry
    player.press("RETURN")  # record
    player.press("Z")  # undo works now
    for key in ("RETURN", "RETURN", "RETURN", "RIGHT", "R"):
        player.press(key)  # fail in replay, then pick retry
    player.press("RIGHT")  # fail again
    player.press("Z")  # and undo it
    game.finish_attempt()
    record = last_record(player.directory)
    assert record["undos"] == 2
    assert record["disabled_presses"] == {"undo": 1, "wait": 1, "retry": 1}
    assert record["failure_choices"] == {"retry": 1, "undo": 1}
    assert record["previews"] == []
    assert record["resets"] == 2
