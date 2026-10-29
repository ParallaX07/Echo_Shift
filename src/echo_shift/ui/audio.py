"""Music and sound effects: a presentation-only reaction to what the game does.

Music plays on channels 0-2 and effects on channel 3, so an effect never cuts a
melody. Nothing here touches the rules or delays input. Without an audio device,
or with a bad data file, one warning is logged and the game carries on silently.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import pyxel

from echo_shift.engine.model import Phase, State
from echo_shift.engine.turn import Failed, Rejected
from echo_shift.paths import resource_path
from echo_shift.ui.progress import MAX_VOLUME, Settings

logger = logging.getLogger(__name__)

MUSIC_CHANNELS = (0, 1, 2)
SFX_CHANNEL = 3
BASE_GAIN = 0.125  # Pyxel's default channel gain, used at full volume
# When a track is absent (or finished), another one stands in or follows it.
FALLBACK = {"clear_sting": "title", "play_replay": "play_calm"}
FOLLOW = {"clear_sting": "title"}


@dataclass(frozen=True)
class Refusal:
    """An input the interface turned down before the rules saw it."""

    reason: str


@dataclass(frozen=True)
class Cue:
    """An effect that replaces the state difference, e.g. after an undo."""

    sfx_id: str


def music_for(
    mode: str, modal: str | None, phase: Phase, level: int, total: int
) -> str:
    """The track id the current screen calls for; chamber `total` ends on `final`."""
    if mode != "game":
        return "title"
    if modal == "result" or phase is Phase.RESULT:
        return "final" if level >= total else "clear_sting"
    return "play_replay" if phase is Phase.REPLAY else "play_calm"


def _over_budget(reason: str) -> bool:
    text = reason.lower()
    return "capacity" in text or "budget" in text


def _gained(before: frozenset[str], after: frozenset[str]) -> bool:
    return bool(after - before)


def _lost(before: frozenset[str], after: frozenset[str]) -> bool:
    return bool(before - after)


def sfx_for(prev: State, result: object, new: State) -> str | None:
    """The one effect that best describes this step, or None for silence.

    `result` is an engine result, a `Refusal`, a `Cue`, a UI cue (an effect id as
    text) or None. Priority: fail, a `Cue` (it replaces the state difference),
    clear, reject, an energy cell pickup, record/commit/launch, echo expiry,
    gate, elevator, pad, power, then move/wait (a recorded step ticks instead).
    A UI cue only sounds when the state itself changed in no audible way.
    """
    if isinstance(result, Failed):
        return "fail"
    if isinstance(result, Cue):
        return result.sfx_id
    if new.phase is Phase.RESULT and prev.phase is not Phase.RESULT:
        return "clear"
    if isinstance(result, Rejected | Refusal):
        return "over_budget" if _over_budget(result.reason) else "reject"
    cue = result if isinstance(result, str) else None
    if prev.chamber is not new.chamber:
        return cue  # a different chamber was loaded; nothing happened in it
    return _diff(prev, new) or cue


def _diff(prev: State, new: State) -> str | None:
    if new.cells_taken - prev.cells_taken:
        return "pickup"
    phases = (prev.phase, new.phase)
    if phases == (Phase.PREPARE, Phase.RECORDING):
        return "record_start"
    if phases == (Phase.RECORDING, Phase.COMMITTED):
        return "commit"
    if new.phase is Phase.REPLAY and (
        prev.phase is not Phase.REPLAY or new.echo_index < prev.echo_index
    ):
        return "launch"
    if (
        phases == (Phase.REPLAY, Phase.REPLAY)
        and prev.echo_position is not None
        and new.echo_position is None
    ):
        return "echo_expire"
    if _gained(prev.gates_open, new.gates_open):
        return "gate_open"
    if _lost(prev.gates_open, new.gates_open):
        return "gate_close"
    if _gained(prev.elevators_running, new.elevators_running):
        return "elevator_start"
    if _gained(prev.pad_active, new.pad_active):
        return "pad_on"
    if _lost(prev.pad_active, new.pad_active):
        return "pad_off"
    if _gained(prev.powered_circuits, new.powered_circuits):
        return "power_on"
    if _lost(prev.powered_circuits, new.powered_circuits):
        return "power_off"
    if len(new.recording) > len(prev.recording):
        return "record_tick"
    if new.player != prev.player:
        return "move"
    if new.turns > prev.turns:
        return "wait"
    return None


@dataclass(frozen=True)
class Track:
    sounds: tuple
    loop: bool


class Audio:
    """Loaded sounds plus playback; every device call is guarded."""

    def __init__(self, player=pyxel, directory: Path | None = None) -> None:
        self.player = player
        self.enabled = True
        self.warned = False
        self.music: dict[str, Track] = {}
        self.sfx: dict[str, object] = {}
        self.current: str | None = None  # the track id last asked for
        self.target: str | None = None  # the screen's track, to spot changes
        self.applied: tuple | None = None
        folder = directory or resource_path("assets", "audio")
        self.guard(self.load, folder)

    def warn(self, message: str, error: object) -> None:
        """Log the first failure; later ones stay quiet so a frame loop can't flood."""
        if not self.warned:
            self.warned = True
            logger.warning("audio unavailable: %s: %s", message, error)

    def guard(self, call, *args) -> None:
        if not self.enabled:
            return
        try:
            call(*args)
        except Exception as error:  # noqa: BLE001 - audio must never stop the game
            self.warn(getattr(call, "__name__", "call"), error)
            self.enabled = False

    def read(self, folder: Path, name: str) -> dict:
        path = folder / name
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            self.warn(name, error)
            return {}
        return data if isinstance(data, dict) else {}

    def build(self, code: str):
        sound = self.player.Sound()
        sound.mml(code)
        return sound

    def load(self, folder: Path) -> None:
        for name, code in self.read(folder, "sfx.json").items():
            try:
                self.sfx[name] = self.build(code)
            except Exception as error:  # noqa: BLE001 - skip one bad effect
                self.warn(f"effect {name}", error)
        for name, entry in self.read(folder, "music.json").items():
            try:
                codes = entry["mml"][: len(MUSIC_CHANNELS)]
                sounds = tuple(self.build(code) for code in codes)
                self.music[name] = Track(sounds, bool(entry.get("loop", True)))
            except Exception as error:  # noqa: BLE001 - skip one bad track
                self.warn(f"track {name}", error)

    def apply_settings(self, settings: Settings) -> None:
        """Set channel volumes from the settings; mute silences without stopping."""
        key = (settings.music_volume, settings.sfx_volume, settings.mute)
        if key == self.applied:
            return
        self.applied = key
        self.guard(self.set_gains, *key)

    def set_gains(self, music: int, sfx: int, mute: bool) -> None:
        for channel in range(SFX_CHANNEL + 1):
            volume = music if channel in MUSIC_CHANNELS else sfx
            self.player.channels[channel].gain = (
                0.0 if mute else BASE_GAIN * volume / MAX_VOLUME
            )

    def play_music(self, track_id: str | None) -> None:
        """Cut to a track at once; an unknown id (or None) just stops the music."""
        self.current = track_id
        self.guard(self.start_music, track_id)

    def start_music(self, track_id: str | None) -> None:
        for channel in MUSIC_CHANNELS:
            self.player.stop(channel)
        if track_id not in self.music and track_id in FALLBACK:
            self.current = track_id = FALLBACK[track_id]
        track = self.music.get(track_id)
        if track is None:
            return
        for channel, sound in zip(MUSIC_CHANNELS, track.sounds, strict=False):
            self.player.play(channel, sound, loop=track.loop)

    def sync_music(self, wanted: str | None) -> None:
        """Switch when the screen's track changes; follow a finished one."""
        if wanted != self.target:
            self.target = wanted
            self.play_music(wanted)
        elif self.current in FOLLOW and self.current in self.music:
            self.guard(self.follow)

    def follow(self) -> None:
        if all(self.player.play_pos(ch) is None for ch in MUSIC_CHANNELS):
            self.play_music(FOLLOW[self.current])

    def play_sfx(self, sfx_id: str | None) -> None:
        sound = self.sfx.get(sfx_id)
        if sound is not None:
            self.guard(self.player.play, SFX_CHANNEL, sound)

    def on_transition(self, prev: State, result: object, new: State) -> str | None:
        """Play the effect for one step of the game and return its id."""
        sfx_id = sfx_for(prev, result, new)
        self.play_sfx(sfx_id)
        return sfx_id
