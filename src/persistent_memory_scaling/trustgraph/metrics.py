"""External TG-1 resource accounting with explicit units and provenance."""

from __future__ import annotations

import json
import re
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .preflight import write_json


_UNITS = {
    "B": 1,
    "KB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
    "TB": 1000**4,
    "KIB": 1024,
    "MIB": 1024**2,
    "GIB": 1024**3,
    "TIB": 1024**4,
}


def parse_bytes(value: str) -> int:
    value = value.strip()
    if value in {"", "0B"}:
        return 0
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([KMGT]?i?B)", value, re.I)
    if not match:
        raise ValueError(f"unsupported byte value: {value!r}")
    return round(float(match.group(1)) * _UNITS[match.group(2).upper()])


def parse_pair(value: str) -> tuple[int, int]:
    left, right = value.split("/", 1)
    return parse_bytes(left), parse_bytes(right)


def _run(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def _json_lines(value: str) -> list[dict[str, Any]]:
    rows = []
    for line in value.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def collect_containers(project: str) -> list[dict[str, Any]]:
    listed = _run(["docker", "ps", "--filter", f"label=com.docker.compose.project={project}", "--format", "{{.ID}}"])
    ids = [line for line in listed.stdout.splitlines() if line]
    if not ids:
        return []
    stats = _run(["docker", "stats", "--no-stream", "--format", "{{json .}}", *ids], timeout=120)
    if stats.returncode:
        raise RuntimeError(stats.stderr.strip() or "docker stats failed")
    result = []
    for row in _json_lines(stats.stdout):
        memory, memory_limit = parse_pair(row["MemUsage"])
        net_rx, net_tx = parse_pair(row["NetIO"])
        block_read, block_write = parse_pair(row["BlockIO"])
        result.append({
            "container": row["Name"],
            "container_id": row["ID"],
            "cpu_percent": float(row["CPUPerc"].rstrip("%")),
            "memory_bytes": memory,
            "memory_limit_bytes": memory_limit,
            "memory_percent": float(row["MemPerc"].rstrip("%")),
            "network_rx_bytes": net_rx,
            "network_tx_bytes": net_tx,
            "block_read_bytes": block_read,
            "block_write_bytes": block_write,
            "pids": int(row["PIDs"]),
            "source": "docker stats --no-stream"
        })
    return sorted(result, key=lambda item: item["container"])


def collect_volumes(project: str) -> list[dict[str, Any]]:
    listed = _run(["docker", "volume", "ls", "--filter", f"label=com.docker.compose.project={project}", "--format", "{{.Name}}"])
    result = []
    for name in sorted(line for line in listed.stdout.splitlines() if line):
        inspected = _run(["docker", "volume", "inspect", name, "--format", "{{.Mountpoint}}"])
        mountpoint = inspected.stdout.strip()
        # Docker's data root is normally unreadable to an unprivileged host
        # user.  Measure through a short-lived read-only mount instead of sudo.
        measured = _run([
            "docker", "run", "--rm", "--mount",
            f"type=volume,source={name},target=/data,readonly",
            "alpine:3.23.2", "du", "-sk", "/data"
        ]) if mountpoint else None
        if measured and measured.returncode == 0:
            physical_bytes = int(measured.stdout.split()[0]) * 1024
            error = None
        else:
            physical_bytes = None
            error = (measured.stderr.strip() if measured else "missing mountpoint")
        result.append({
            "volume": name,
            "mountpoint": mountpoint,
            "physical_bytes": physical_bytes,
            "measurement_error": error,
            "source": "BusyBox du -sk through ephemeral read-only volume mount; converted KiB to bytes"
        })
    return result


def collect_gpu() -> dict[str, Any]:
    query = "index,uuid,name,memory.used,memory.total,utilization.gpu"
    result = _run(["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"])
    if result.returncode:
        return {"available": False, "error": result.stderr.strip(), "devices": []}
    devices = []
    for line in result.stdout.splitlines():
        index, uuid, name, used, total, utilization = [part.strip() for part in line.split(",")]
        devices.append({"index": int(index), "uuid": uuid, "name": name, "memory_used_bytes": int(used) * 1024**2,
                        "memory_total_bytes": int(total) * 1024**2, "utilization_percent": int(utilization)})
    trustgraph_ids = _trustgraph_container_ids()
    processes_result = _run([
        "nvidia-smi", "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory",
        "--format=csv,noheader,nounits"
    ])
    processes = []
    if processes_result.returncode == 0:
        for line in processes_result.stdout.splitlines():
            parts = [part.strip() for part in line.split(",", 3)]
            if len(parts) == 4 and parts[1].isdigit() and parts[3].isdigit():
                identity = _process_identity(int(parts[1]))
                attribution = classify_gpu_process(identity, trustgraph_ids)
                processes.append({"gpu_uuid": parts[0], "pid": int(parts[1]), "process_name": parts[2],
                                  "memory_used_bytes": int(parts[3]) * 1024**2,
                                  "attribution": attribution, "identity": identity})
    attributed = {name: sum(item["memory_used_bytes"] for item in processes
                            if item["attribution"] == name)
                  for name in ("asm", "trustgraph", "other")}
    attributed["unattributed"] = max(0, sum(item["memory_used_bytes"] for item in devices)
                                      - sum(attributed.values()))
    return {"available": True, "devices": devices, "processes": processes,
            "attribution_memory_bytes": attributed,
            "process_query_error": processes_result.stderr.strip() or None if processes_result.returncode else None,
            "source": "nvidia-smi plus read-only /proc PID identity and Docker cgroup attribution"}


def _trustgraph_container_ids(project: str = "generated") -> set[str]:
    result = _run(["docker", "ps", "--filter", f"label=com.docker.compose.project={project}",
                   "--format", "{{.ID}}"])
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def _read_proc(pid: int, name: str, binary: bool = False) -> str:
    try:
        value = Path(f"/proc/{pid}/{name}").read_bytes()
        return value.replace(b"\0", b" ").decode(errors="replace").strip() if binary else value.decode(errors="replace").strip()
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return ""


def _process_identity(pid: int) -> dict[str, str]:
    try:
        cwd = str(Path(f"/proc/{pid}/cwd").resolve())
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        cwd = ""
    return {"cmdline": _read_proc(pid, "cmdline", binary=True), "cgroup": _read_proc(pid, "cgroup"),
            "cwd": cwd}


def classify_gpu_process(identity: dict[str, str], trustgraph_ids: set[str]) -> str:
    cgroup = identity.get("cgroup", "").lower()
    if any(container_id.lower() in cgroup for container_id in trustgraph_ids):
        return "trustgraph"
    text = " ".join(identity.values()).lower()
    if "asm-memory-bridge" in text or re.search(r"(?:^|[ /])asm(?:[ /]|$)", text):
        return "asm"
    return "other"


def sample_window(window_id: str, phase: str, duration: float, interval: float,
                  project: str = "generated", include_gpu: bool = True) -> dict[str, Any]:
    if duration <= 0 or interval <= 0:
        raise ValueError("duration and interval must be positive")
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    samples = []
    while True:
        containers = collect_containers(project)
        gpu = collect_gpu() if include_gpu else {"devices": [], "processes": [], "excluded": True}
        samples.append({
            "elapsed_seconds": time.monotonic() - started,
            "container_memory_bytes": sum(item["memory_bytes"] for item in containers),
            "container_cpu_percent": sum(item["cpu_percent"] for item in containers),
            "gpu_memory_used_bytes": sum(item["memory_used_bytes"] for item in gpu.get("devices", [])),
            "gpu_processes": gpu.get("processes", []),
            "gpu_attribution_memory_bytes": gpu.get("attribution_memory_bytes", {}),
            "containers": containers,
        })
        remaining = duration - (time.monotonic() - started)
        if remaining <= 0:
            break
        time.sleep(min(interval, remaining))
    memory_values = [item["container_memory_bytes"] for item in samples]
    gpu_values = [item["gpu_memory_used_bytes"] for item in samples]
    attribution = {}
    if include_gpu:
        for name in ("asm", "trustgraph", "other", "unattributed"):
            values = [item["gpu_attribution_memory_bytes"].get(name, 0) for item in samples]
            attribution[name] = {"min_bytes": min(values), "mean_bytes": statistics.fmean(values),
                                 "peak_bytes": max(values)}
    return {
        "schema_version": "tg-metrics-window-v1",
        "window_id": window_id,
        "phase": phase,
        "started_at": started_at,
        "duration_requested_seconds": duration,
        "duration_observed_seconds": time.monotonic() - started,
        "interval_seconds": interval,
        "gpu_included": include_gpu,
        "sample_count": len(samples),
        "samples": samples,
        "summary": {
            "container_memory_min_bytes": min(memory_values),
            "container_memory_mean_bytes": statistics.fmean(memory_values),
            "container_memory_peak_bytes": max(memory_values),
            "gpu_memory_min_bytes": min(gpu_values),
            "gpu_memory_mean_bytes": statistics.fmean(gpu_values),
            "gpu_memory_peak_bytes": max(gpu_values),
            "gpu_attribution": attribution,
        },
    }


def aggregate_deltas(values: list[dict[str, Any]]) -> dict[str, Any]:
    if len(values) < 2:
        raise ValueError("at least two delta files are required")
    keys = ("container_memory_bytes", "volume_physical_bytes")
    t95 = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776}.get(len(values), 1.96)
    metrics = {}
    for key in keys:
        observations = [float(item["totals"][key]) for item in values]
        mean = statistics.fmean(observations)
        stdev = statistics.stdev(observations)
        margin = t95 * stdev / len(observations) ** 0.5
        metrics[key] = {"observations": observations, "mean": mean, "stdev": stdev,
                        "ci95_low": mean - margin, "ci95_high": mean + margin}
    return {"schema_version": "tg-metrics-aggregate-v1", "repetitions": len(values),
            "confidence_method": "two-sided Student t approximation", "metrics": metrics}


def summarize_observations(observations: list[float]) -> dict[str, Any]:
    if len(observations) < 2:
        raise ValueError("at least two observations are required")
    mean = statistics.fmean(observations)
    stdev = statistics.stdev(observations)
    t95 = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776}.get(len(observations), 1.96)
    margin = t95 * stdev / len(observations) ** 0.5
    return {"observations": observations, "mean": mean, "stdev": stdev,
            "ci95_low": mean - margin, "ci95_high": mean + margin}


def aggregate_official_cycles(manifests: list[dict[str, Any]],
                              windows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    if len(manifests) < 2 or any(not item.get("valid") for item in manifests):
        raise ValueError("official aggregate requires at least two valid cycles")
    result: dict[str, Any] = {
        "schema_version": "tg1-official-aggregate-v1",
        "run_ids": [item["run_id"] for item in manifests],
        "repetitions": len(manifests),
        "confidence_method": "two-sided Student t approximation",
        "matched": {}, "queries": {}, "phases": {},
    }
    for key in ("container_memory_bytes", "volume_physical_bytes"):
        result["matched"][key] = summarize_observations(
            [float(item["matched_delta"]["totals"][key]) for item in manifests])
    for phase in ("cold", "warm"):
        result["queries"][phase] = {}
        for key in ("mean_seconds", "p50_seconds", "p95_seconds", "max_seconds"):
            result["queries"][phase][key] = summarize_observations(
                [float(item[phase][key]) for item in manifests])
    for phase, phase_windows in windows.items():
        result["phases"][phase] = {}
        extractors = {
            "container_cpu_mean_percent": lambda value: statistics.fmean(
                sample["container_cpu_percent"] for sample in value["samples"]),
            "container_cpu_peak_percent": lambda value: max(
                sample["container_cpu_percent"] for sample in value["samples"]),
            "container_memory_mean_bytes": lambda value: value["summary"]["container_memory_mean_bytes"],
            "container_memory_peak_bytes": lambda value: value["summary"]["container_memory_peak_bytes"],
            "trustgraph_vram_peak_bytes": lambda value: value["summary"]["gpu_attribution"]["trustgraph"]["peak_bytes"],
            "asm_vram_mean_bytes": lambda value: value["summary"]["gpu_attribution"]["asm"]["mean_bytes"],
        }
        for key, extract in extractors.items():
            result["phases"][phase][key] = summarize_observations(
                [float(extract(value)) for value in phase_windows])
    return result


def matched_delta(control: dict[str, Any], loaded: dict[str, Any]) -> dict[str, Any]:
    """Subtract an equal-duration empty control from a loaded phase delta."""
    if control["event_delta"] != loaded["event_delta"]:
        raise ValueError("control and loaded event_delta must match")
    totals = {key: loaded["totals"][key] - control["totals"][key]
              for key in ("container_memory_bytes", "volume_physical_bytes")}
    events = loaded["event_delta"]
    return {
        "schema_version": "tg-metrics-matched-delta-v1",
        "control": {"before": control["before"], "after": control["after"], "totals": control["totals"]},
        "loaded": {"before": loaded["before"], "after": loaded["after"], "totals": loaded["totals"]},
        "event_delta": events,
        "totals": totals,
        "per_event": {f"{key}_per_event": value / events for key, value in totals.items()},
        "rule": "equal-duration loaded delta minus equal-duration empty-control delta",
    }


def collect_prometheus(container: str = "generated-prometheus-1") -> dict[str, Any]:
    url = 'http://localhost:9090/api/v1/query?query=%7B__name__%3D~%22tg_.%2A%22%7D'
    result = _run(["docker", "exec", container, "wget", "-qO-", url])
    if result.returncode:
        return {"available": False, "series": [], "error": result.stderr.strip()}
    try:
        payload = json.loads(result.stdout)
        series = payload.get("data", {}).get("result", [])
        return {"available": True, "series": series, "series_count": len(series), "source": "Prometheus instant query tg_.*"}
    except json.JSONDecodeError as exc:
        return {"available": False, "series": [], "error": str(exc)}


def collect_backend_logical() -> dict[str, Any]:
    qdrant = _run([
        "docker", "run", "--rm", "--network", "generated_default",
        "alpine:3.23.2", "wget", "-qO-", "http://qdrant:6333/collections"
    ])
    cassandra = _run(["docker", "exec", "generated-cassandra-1", "nodetool", "tablestats"], timeout=120)
    cassandra_schema = None
    if cassandra.returncode:
        cassandra_schema = _run([
            "docker", "exec", "generated-cassandra-1", "cqlsh", "-e",
            "SELECT keyspace_name, table_name FROM system_schema.tables;"
        ], timeout=120)
    return {
        "qdrant_collections": json.loads(qdrant.stdout) if qdrant.returncode == 0 and qdrant.stdout else None,
        "qdrant_error": (qdrant.stderr.strip() or "qdrant query failed") if qdrant.returncode else None,
        "cassandra_tablestats": cassandra.stdout if cassandra.returncode == 0 else None,
        "cassandra_schema": cassandra_schema.stdout if cassandra_schema and cassandra_schema.returncode == 0 else None,
        "cassandra_error": (cassandra.stderr.strip() or "nodetool tablestats failed") if cassandra.returncode else None,
        "cassandra_fallback": "system_schema.tables via cqlsh" if cassandra_schema else None,
        "note": "logical backend data; never added to physical volume bytes"
    }


def snapshot(snapshot_id: str, phase: str, project: str = "generated", include_gpu: bool = True) -> dict[str, Any]:
    containers = collect_containers(project)
    volumes = collect_volumes(project)
    physical_values = [item["physical_bytes"] for item in volumes if item["physical_bytes"] is not None]
    return {
        "schema_version": "tg-metrics-snapshot-v1",
        "snapshot_id": snapshot_id,
        "phase": phase,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "containers": containers,
        "volumes": volumes,
        "gpu": collect_gpu() if include_gpu else {"excluded": True, "reason": "explicit CLI selection"},
        "prometheus": collect_prometheus(),
        "backend_logical": collect_backend_logical(),
        "totals": {
            "container_memory_bytes": sum(item["memory_bytes"] for item in containers),
            "volume_physical_bytes": sum(physical_values),
            "volume_measurement_count": len(physical_values),
            "container_count": len(containers),
        },
    }


def delta(before: dict[str, Any], after: dict[str, Any], event_delta: int) -> dict[str, Any]:
    if event_delta <= 0:
        raise ValueError("event_delta must be positive")
    keys = ("container_memory_bytes", "volume_physical_bytes")
    totals = {key: after["totals"][key] - before["totals"][key] for key in keys}
    before_containers = {item["container"]: item for item in before.get("containers", [])}
    before_volumes = {item["volume"]: item for item in before.get("volumes", [])}
    by_container = []
    for item in after.get("containers", []):
        previous = before_containers.get(item["container"], {})
        by_container.append({
            "container": item["container"],
            "memory_delta_bytes": item["memory_bytes"] - previous.get("memory_bytes", 0),
            "block_read_delta_bytes": item["block_read_bytes"] - previous.get("block_read_bytes", 0),
            "block_write_delta_bytes": item["block_write_bytes"] - previous.get("block_write_bytes", 0),
            "network_rx_delta_bytes": item["network_rx_bytes"] - previous.get("network_rx_bytes", 0),
            "network_tx_delta_bytes": item["network_tx_bytes"] - previous.get("network_tx_bytes", 0),
        })
    by_volume = []
    for item in after.get("volumes", []):
        previous = before_volumes.get(item["volume"], {})
        current_bytes = item.get("physical_bytes")
        previous_bytes = previous.get("physical_bytes")
        by_volume.append({"volume": item["volume"], "physical_delta_bytes":
                          current_bytes - previous_bytes if current_bytes is not None and previous_bytes is not None else None})
    return {
        "schema_version": "tg-metrics-delta-v1",
        "before": before["snapshot_id"],
        "after": after["snapshot_id"],
        "event_delta": event_delta,
        "totals": totals,
        "per_event": {f"{key}_per_event": value / event_delta for key, value in totals.items()},
        "by_container": sorted(by_container, key=lambda item: item["container"]),
        "by_volume": sorted(by_volume, key=lambda item: item["volume"]),
        "accounting": {
            "shared_infrastructure": ["pulsar", "bookie", "zookeeper", "prometheus", "loki", "grafana", "control", "api-gateway"],
            "collection_backends": ["cassandra", "qdrant", "garage-data", "garage-meta"],
            "rule": "component deltas are reported separately; allocation to a collection requires a matched empty control"
        },
        "warning": "RSS delta includes runtime/cache effects and is not logical retained-state size",
    }


def write_snapshot(path: Path, snapshot_value: dict[str, Any]) -> None:
    write_json(path, snapshot_value)
