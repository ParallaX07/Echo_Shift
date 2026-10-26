"""Audition Pyxel gen_bgm candidates and keep the good ones.

Keys: Right/Left next/previous, Space replay or stop, K keep, Q quit.
Kept candidates are merged into tmp/music_candidates.json.
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tmp/music_candidates.json"
PARAMS = ("preset", "transp", "instr", "seed")
LIMITS = {"preset": (0, 7), "transp": (-5, 5), "instr": (0, 3)}


def parse_range(text: str, low: int = 0, high: int | None = None) -> list[int]:
    """Parse "3", "1-20" or "1,4,7-9" into a list of ints, in order."""
    values: list[int] = []
    for part in text.split(","):
        start, dash, end = part.strip().partition("-")
        if start == "" and dash:  # a negative single number such as "-3"
            start, end = f"-{end}", ""
        first = int(start)
        last = int(end) if end else first
        if last < first:
            raise ValueError(f"empty range: {part!r}")
        values.extend(range(first, last + 1))
    if high is not None and not all(low <= value <= high for value in values):
        raise ValueError(f"{text!r} is outside {low}-{high}")
    return values


def sweep(presets: list[int], instrs: list[int], seeds: list[int], transp: int = 0):
    """Every candidate as a parameter dict: preset, then instrument, then seed."""
    return [
        {"preset": preset, "transp": transp, "instr": instr, "seed": seed}
        for preset in presets
        for instr in instrs
        for seed in seeds
    ]


def key_of(entry: dict) -> tuple:
    return tuple(entry[name] for name in PARAMS)


def merge_kept(path: Path, new: list[dict]) -> list[dict]:
    """Add new keeps to the file at path, skipping parameters already there."""
    kept = json.loads(path.read_text()) if path.exists() else []
    seen = {key_of(entry) for entry in kept}
    for entry in new:
        if key_of(entry) not in seen:
            seen.add(key_of(entry))
            kept.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(kept, indent=2) + "\n")
    return kept


def audition(candidates: list[dict], context: str | None) -> None:
    import pyxel

    class Window:
        def __init__(self) -> None:
            pyxel.init(256, 96, title="Audition music", fps=30)
            self.index = 0
            self.playing = False
            self.mml: list[str] = []
            self.kept = {
                key_of(entry)
                for entry in (json.loads(OUTPUT.read_text()) if OUTPUT.exists() else [])
            }
            self.load()
            pyxel.run(self.update, self.draw)

        def load(self) -> None:
            """Generate the current candidate and start it."""
            params = candidates[self.index]
            self.mml = pyxel.gen_bgm(*(params[name] for name in PARAMS))
            self.play()

        def play(self) -> None:
            pyxel.stop()
            for channel, code in enumerate(self.mml):
                pyxel.sounds[channel].mml(code)
                pyxel.play(channel, channel, loop=True)
            self.playing = True

        def move(self, step: int) -> None:
            self.index = (self.index + step) % len(candidates)
            self.load()

        def keep(self) -> None:
            entry = {
                **candidates[self.index],
                "pyxel_version": pyxel.VERSION,
                "mml": self.mml,
            }
            if context:
                entry["context"] = context
            merge_kept(OUTPUT, [entry])
            self.kept.add(key_of(entry))

        def update(self) -> None:
            if pyxel.btnp(pyxel.KEY_Q):
                pyxel.stop()
                pyxel.quit()
            elif pyxel.btnp(pyxel.KEY_RIGHT, 20, 10):
                self.move(1)
            elif pyxel.btnp(pyxel.KEY_LEFT, 20, 10):
                self.move(-1)
            elif pyxel.btnp(pyxel.KEY_SPACE):
                if self.playing:
                    pyxel.stop()
                    self.playing = False
                else:
                    self.play()
            elif pyxel.btnp(pyxel.KEY_K):
                self.keep()

        def draw(self) -> None:
            params = candidates[self.index]
            pyxel.cls(0)
            pyxel.text(8, 8, f"{self.index + 1} / {len(candidates)}", 7)
            pyxel.text(8, 20, "  ".join(f"{n} {params[n]}" for n in PARAMS), 7)
            pyxel.text(8, 32, "playing" if self.playing else "stopped", 6)
            if key_of(params) in self.kept:
                pyxel.text(8, 44, "kept", 11)
            pyxel.text(8, 64, "Left/Right  Space play/stop", 13)
            pyxel.text(8, 76, "K keep      Q quit", 13)

    Window()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--presets", default="0-7", help="e.g. 0-7 or 1,3")
    parser.add_argument("--instrs", default="0-3", help="e.g. 0-3 or 2")
    parser.add_argument("--seeds", default="1-20", help="e.g. 1-20")
    parser.add_argument("--transp", type=int, default=0, help="transposition, -5..5")
    parser.add_argument("--context", help="label stored with kept candidates")
    args = parser.parse_args()
    try:
        presets = parse_range(args.presets, *LIMITS["preset"])
        instrs = parse_range(args.instrs, *LIMITS["instr"])
        seeds = parse_range(args.seeds)
    except ValueError as error:
        parser.error(str(error))
    if not LIMITS["transp"][0] <= args.transp <= LIMITS["transp"][1]:
        parser.error("--transp must be between -5 and 5")
    audition(sweep(presets, instrs, seeds, args.transp), args.context)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
