from echo_shift.engine import power


def test_at_capacity_is_accepted(chamber_factory):
    chamber = chamber_factory()
    assert power.apply(chamber, frozenset({"lab-power"})).ok


def test_one_over_capacity_is_rejected(chamber_factory):
    chamber = chamber_factory(capacity=1)
    result = power.apply(chamber, frozenset({"lab-power"}))
    assert not result.ok
    assert result.circuits == frozenset()


def test_power_load_is_independent_of_configuration_order(chamber_factory):
    from dataclasses import replace

    from echo_shift.engine.model import Circuit

    chamber = chamber_factory(capacity=3)
    chamber = replace(
        chamber,
        circuits=(Circuit("a", 1), Circuit("b", 2)),
        devices=(),
    )
    assert power.apply(chamber, frozenset({"a", "b"})) == power.apply(
        chamber, frozenset({"b", "a"})
    )
