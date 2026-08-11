"""Reproducible TG-1 runner with matched controls and automatic rejection."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .client import TrustGraphClient
from .metrics import (collect_volumes, delta, matched_delta, sample_window,
                      snapshot)
from .preflight import write_json
from .workload import BASE, generate_smoke_workload


COMPOSE_FILES = ("configs/trustgraph/generated/docker-compose.yaml",
                 "configs/trustgraph/compose.tg0.override.yaml")


def validate_cycle(control: dict[str, Any], container_sets: list[set[str]],
                   max_control_disk_bytes: int) -> list[str]:
    reasons = []
    if control["totals"]["volume_physical_bytes"] > max_control_disk_bytes:
        reasons.append("empty_control_disk_growth_exceeded")
    if not container_sets or len(container_sets[0]) != 21:
        reasons.append("unexpected_container_count")
    if any(ids != container_sets[0] for ids in container_sets[1:]):
        reasons.append("container_restart_detected")
    return reasons


class TG1Runner:
    def __init__(self, root: Path, token: str, stabilization_seconds: float,
                 phase_seconds: float, query_seconds: float,
                 max_control_disk_bytes: int) -> None:
        self.root = root
        self.token = token
        self.stabilization_seconds = stabilization_seconds
        self.phase_seconds = phase_seconds
        self.query_seconds = query_seconds
        self.max_control_disk_bytes = max_control_disk_bytes
        self.raw = root / "results/raw"
        self.raw.mkdir(parents=True, exist_ok=True)
        self.compose = ["docker", "compose"]
        for path in COMPOSE_FILES:
            self.compose += ["-f", path]
        self.env = os.environ | {
            "IAM_BOOTSTRAP_TOKEN": token,
            "GF_SECURITY_ADMIN_PASSWORD": "pmsb-tg1-local",
            "OLLAMA_HOST": "http://172.19.0.1:11435",
        }

    def command(self, args: list[str], timeout: int = 180) -> str:
        result = subprocess.run(args, cwd=self.root, env=self.env, text=True,
                                capture_output=True, timeout=timeout, check=False)
        if result.returncode:
            raise RuntimeError(f"command failed ({result.returncode}): {' '.join(args)}\n{result.stderr}")
        return result.stdout

    def fresh_stack(self) -> None:
        self.command(self.compose + ["down", "--volumes", "--remove-orphans"], timeout=180)
        self.command(self.compose + ["up", "-d"], timeout=180)

    def stop_preserving_volumes(self) -> None:
        self.command(self.compose + ["down"], timeout=180)

    def wait_ready(self, timeout: float = 180) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            pulsar = subprocess.run(["docker", "exec", "generated-pulsar-1", "bin/pulsar-admin",
                                     "namespaces", "list", "tg"], capture_output=True, text=True)
            cassandra = subprocess.run(["docker", "exec", "generated-cassandra-1", "cqlsh", "-e",
                                        "DESCRIBE KEYSPACES"], capture_output=True, text=True)
            if pulsar.returncode == 0 and "tg/notify" in pulsar.stdout and cassandra.returncode == 0:
                client = TrustGraphClient("http://localhost:8888/", self.token, timeout=30)
                try:
                    client.list_flows()
                    return
                except Exception:
                    pass
            time.sleep(5)
        raise TimeoutError("TrustGraph did not pass Pulsar, Cassandra and API health checks")

    @staticmethod
    def volume_total() -> int:
        return sum(item["physical_bytes"] or 0 for item in collect_volumes("generated"))

    def stabilize(self) -> dict[str, Any]:
        started = time.monotonic()
        time.sleep(self.stabilization_seconds)
        first = self.volume_total()
        time.sleep(15)
        second = self.volume_total()
        return {"minimum_seconds": self.stabilization_seconds,
                "observed_seconds": time.monotonic() - started,
                "first_volume_bytes": first, "second_volume_bytes": second,
                "growth_bytes": second - first,
                "quiescent": second - first <= self.max_control_disk_bytes}

    def ensure_flow(self, client: TrustGraphClient, timeout: float = 180) -> None:
        try:
            client.start_flow("qwen2.5:0.5b", "sentence-transformers/all-MiniLM-L6-v2")
        except Exception:
            # A timed-out lifecycle request may still have been committed. Poll
            # the public API before deciding that startup failed.
            pass
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if client.flow_id in client.list_flows():
                    return
            except Exception:
                pass
            time.sleep(5)
        raise TimeoutError(f"flow {client.flow_id!r} was not confirmed before baseline")

    def save_snapshot(self, run_id: str, phase: str) -> dict[str, Any]:
        value = snapshot(f"{run_id}-{phase}", phase)
        write_json(self.raw / f"{run_id}-{phase}.json", value)
        return value

    def measured_window(self, run_id: str, phase: str, duration: float,
                        action: Callable[[], Any] | None = None) -> tuple[dict[str, Any], Any]:
        result = None
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(action) if action else None
            window = sample_window(f"{run_id}-{phase}-window", phase, duration, 1)
            if future:
                result = future.result(timeout=max(180, duration + 120))
        write_json(self.raw / f"{run_id}-{phase}-window.json", window)
        return window, result

    def run_cycle(self, run_id: str) -> dict[str, Any]:
        self.fresh_stack()
        self.wait_ready()
        client = TrustGraphClient("http://localhost:8888/", self.token, flow_id=run_id,
                                  collection=run_id, timeout=30)
        self.ensure_flow(client)
        stabilization = self.stabilize()
        baseline = self.save_snapshot(run_id, "empty-start")
        empty_window, _ = self.measured_window(run_id, "empty-control", self.phase_seconds)
        empty_end = self.save_snapshot(run_id, "empty-end")

        workload = generate_smoke_workload()

        def ingest() -> dict[str, Any]:
            triples = client.import_events(workload["events"])
            client.wait_for_subject(f"{BASE}:person:000", 2, 180)
            client.wait_for_subject(f"{BASE}:person:099", 2, 180)
            return {"events": len(workload["events"]), "triples": triples}

        loaded_window, ingest_result = self.measured_window(run_id, "loaded", self.phase_seconds, ingest)
        loaded_end = self.save_snapshot(run_id, "loaded-end")
        control_delta = delta(baseline, empty_end, 100)
        loaded_delta = delta(empty_end, loaded_end, 100)
        adjusted = matched_delta(control_delta, loaded_delta)

        def queries() -> dict[str, Any]:
            latencies = []
            for index in range(100):
                started = time.monotonic()
                rows = client.query_subject(f"{BASE}:person:{index:03d}")
                if len(rows) < 2:
                    raise RuntimeError(f"query {index} returned {len(rows)} triples")
                latencies.append(time.monotonic() - started)
            ordered = sorted(latencies)
            return {"count": len(ordered), "mean_seconds": sum(ordered) / len(ordered),
                    "p50_seconds": ordered[50], "p95_seconds": ordered[95],
                    "max_seconds": ordered[-1]}

        cold_window, cold = self.measured_window(run_id, "cold", self.query_seconds, queries)
        warm_window, warm = self.measured_window(run_id, "warm", self.query_seconds, queries)
        container_sets = [{item["container_id"] for item in snap["containers"]}
                          for snap in (baseline, empty_end, loaded_end)]
        reasons = validate_cycle(control_delta, container_sets, self.max_control_disk_bytes)
        if not stabilization["quiescent"]:
            reasons.append("pre_baseline_disk_not_quiescent")
        manifest = {
            "schema_version": "tg1-official-cycle-v1", "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "valid": not reasons, "rejection_reasons": reasons,
            "parameters": {"stabilization_seconds": self.stabilization_seconds,
                           "phase_seconds": self.phase_seconds, "query_seconds": self.query_seconds,
                           "max_control_disk_bytes": self.max_control_disk_bytes},
            "stabilization": stabilization, "ingest": ingest_result,
            "control_delta": control_delta, "loaded_delta": loaded_delta,
            "matched_delta": adjusted, "cold": cold, "warm": warm,
            "window_summaries": {"empty": empty_window["summary"], "loaded": loaded_window["summary"],
                                 "cold": cold_window["summary"], "warm": warm_window["summary"]},
        }
        write_json(self.raw / f"{run_id}-manifest.json", manifest)
        write_json(self.raw / f"{run_id}-matched-delta.json", adjusted)
        return manifest


def main() -> int:
    parser = argparse.ArgumentParser(prog="pmsb-tg1-run")
    parser.add_argument("--token", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--stabilization", type=float, default=60)
    parser.add_argument("--phase-duration", type=float, default=30)
    parser.add_argument("--query-duration", type=float, default=10)
    parser.add_argument("--max-control-disk-mib", type=float, default=8)
    args = parser.parse_args()
    root = Path.cwd()
    runner = TG1Runner(root, args.token, args.stabilization, args.phase_duration,
                       args.query_duration, round(args.max_control_disk_mib * 1024**2))
    try:
        value = runner.run_cycle(args.run_id)
        print(json.dumps({"run_id": args.run_id, "valid": value["valid"],
                          "rejection_reasons": value["rejection_reasons"],
                          "matched_delta": value["matched_delta"]["totals"]}, indent=2))
        return 0 if value["valid"] else 2
    finally:
        runner.stop_preserving_volumes()


if __name__ == "__main__":
    raise SystemExit(main())
