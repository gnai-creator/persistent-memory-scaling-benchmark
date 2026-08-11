import pytest

from persistent_memory_scaling.trustgraph.scaling_plot import extrapolate_storage


def test_extrapolation_uses_largest_checkpoint_rate_and_scenario_range():
    value = extrapolate_storage([
        {"events": 10_000, "disk_bytes": 180_000_000},
        {"events": 100_000, "disk_bytes": 1_700_000_000},
    ])
    assert value["central_bytes"] == 17_000_000_000
    assert value["scenario_low_bytes"] == 17_000_000_000
    assert value["scenario_high_bytes"] == 18_000_000_000
    assert value["is_measurement"] is False


def test_extrapolation_rejects_target_inside_measurements():
    with pytest.raises(ValueError):
        extrapolate_storage([{"events": 1, "disk_bytes": 1}, {"events": 2, "disk_bytes": 2}], 2)
