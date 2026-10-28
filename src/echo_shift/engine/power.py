"""Circuit capacity validation and power configuration."""

from dataclasses import dataclass

from .model import Chamber, State


@dataclass(frozen=True)
class PowerResult:
    circuits: frozenset[str] = frozenset()
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def capacity_with(chamber: Chamber, cells_taken: frozenset[str]) -> int:
    """Generator capacity once the given energy cells are taken."""
    return chamber.capacity + sum(
        cell.value for cell in chamber.cells if cell.id in cells_taken
    )


def capacity_of(state: State) -> int:
    """Effective generator capacity: the base plus every cell taken so far."""
    return capacity_with(state.chamber, state.cells_taken)


def max_capacity(chamber: Chamber) -> int:
    """Capacity with every cell taken, the most any state can reach."""
    return capacity_with(chamber, frozenset(cell.id for cell in chamber.cells))


def apply(
    chamber: Chamber, config: frozenset[str], capacity: int | None = None
) -> PowerResult:
    """Validate a configuration against `capacity` (the base capacity if omitted)."""
    limit = chamber.capacity if capacity is None else capacity
    known = {circuit.id: circuit for circuit in chamber.circuits}
    unknown = config - known.keys()
    if unknown:
        return PowerResult(error=f"unknown circuit: {min(unknown)}")
    load = sum(known[circuit_id].load for circuit_id in config)
    if load > limit:
        return PowerResult(error=f"power load {load} exceeds capacity {limit}")
    return PowerResult(frozenset(config))
