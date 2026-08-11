import pytest

from persistent_memory_scaling.trustgraph.metrics import (aggregate_deltas, aggregate_official_cycles,
                                                          classify_gpu_process, delta, matched_delta,
                                                          parse_bytes, parse_pair)
from persistent_memory_scaling.trustgraph.tg1_runner import validate_cycle


def test_parse_bytes_decimal_and_binary_units():
    assert parse_bytes("1.5kB") == 1500
    assert parse_bytes("1.5MiB") == 1_572_864
    assert parse_bytes("0B") == 0


def test_parse_pair():
    assert parse_pair("12.5MiB / 1GiB") == (13_107_200, 1_073_741_824)


def test_delta_keeps_disk_and_ram_separate():
    before = {"snapshot_id": "empty", "totals": {"container_memory_bytes": 100, "volume_physical_bytes": 1000}}
    after = {"snapshot_id": "loaded", "totals": {"container_memory_bytes": 120, "volume_physical_bytes": 1500}}
    value = delta(before, after, 100)
    assert value["totals"] == {"container_memory_bytes": 20, "volume_physical_bytes": 500}
    assert value["per_event"]["volume_physical_bytes_per_event"] == 5


def test_aggregate_deltas_has_student_t_interval():
    values = [
        {"totals": {"container_memory_bytes": ram, "volume_physical_bytes": disk}}
        for ram, disk in [(10, 100), (20, 110), (30, 120)]
    ]
    result = aggregate_deltas(values)
    assert result["repetitions"] == 3
    assert result["metrics"]["container_memory_bytes"]["mean"] == 20
    assert result["metrics"]["volume_physical_bytes"]["ci95_low"] < 110


def test_aggregate_requires_repetition():
    with pytest.raises(ValueError, match="at least two"):
        aggregate_deltas([{"totals": {}}])


def test_delta_decomposes_components_when_snapshots_include_them():
    before = {"snapshot_id": "a", "totals": {"container_memory_bytes": 10, "volume_physical_bytes": 20},
              "containers": [{"container": "db", "memory_bytes": 10, "block_read_bytes": 1,
                              "block_write_bytes": 2, "network_rx_bytes": 3, "network_tx_bytes": 4}],
              "volumes": [{"volume": "db", "physical_bytes": 20}]}
    after = {"snapshot_id": "b", "totals": {"container_memory_bytes": 15, "volume_physical_bytes": 27},
             "containers": [{"container": "db", "memory_bytes": 15, "block_read_bytes": 3,
                             "block_write_bytes": 6, "network_rx_bytes": 8, "network_tx_bytes": 10}],
             "volumes": [{"volume": "db", "physical_bytes": 27}]}
    value = delta(before, after, 1)
    assert value["by_container"][0]["memory_delta_bytes"] == 5
    assert value["by_volume"][0]["physical_delta_bytes"] == 7


def test_gpu_process_attribution_uses_cgroup_and_asm_paths():
    assert classify_gpu_process({"cgroup": "docker/abc123", "cmdline": "python"}, {"abc123"}) == "trustgraph"
    assert classify_gpu_process({"cgroup": "user.slice", "cwd": "/work/asm-memory-bridge"}, set()) == "asm"
    assert classify_gpu_process({"cgroup": "user.slice", "cmdline": "firefox"}, set()) == "other"


def test_matched_delta_subtracts_equal_duration_control():
    control = {"before": "a", "after": "b", "event_delta": 100,
               "totals": {"container_memory_bytes": 10, "volume_physical_bytes": 20}}
    loaded = {"before": "b", "after": "c", "event_delta": 100,
              "totals": {"container_memory_bytes": 40, "volume_physical_bytes": 120}}
    value = matched_delta(control, loaded)
    assert value["totals"] == {"container_memory_bytes": 30, "volume_physical_bytes": 100}


def test_cycle_rejects_disk_noise_and_container_restart():
    control = {"totals": {"volume_physical_bytes": 9}}
    reasons = validate_cycle(control, [{str(i) for i in range(21)}, {str(i) for i in range(20)}], 8)
    assert reasons == ["empty_control_disk_growth_exceeded", "container_restart_detected"]


def test_official_aggregate_rejects_invalid_cycle():
    with pytest.raises(ValueError, match="valid cycles"):
        aggregate_official_cycles([{"valid": False}, {"valid": True}], {})
