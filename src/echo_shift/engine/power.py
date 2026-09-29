"""Circuit capacity validation and power configuration."""

from dataclasses import dataclass

from .model import Chamber


@dataclass(frozen=True)
class PowerResult:
    circuits: frozenset[str] = frozenset()
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def apply(chamber: Chamber, config: frozenset[str]) -> PowerResult:
    known = {circuit.id: circuit for circuit in chamber.circuits}
    unknown = config - known.keys()
    if unknown:
        return PowerResult(error=f"unknown circuit: {min(unknown)}")
    load = sum(known[circuit_id].load for circuit_id in config)
    if load > chamber.capacity:
        return PowerResult(
            error=f"power load {load} exceeds capacity {chamber.capacity}"
        )
    return PowerResult(frozenset(config))
