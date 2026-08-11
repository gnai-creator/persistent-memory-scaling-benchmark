"""TG-2 checkpoint runner for deterministic structured storage scaling."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .client import TrustGraphClient
from .metrics import collect_containers, collect_gpu, delta, snapshot
from .preflight import write_json
from .tg1_runner import TG1Runner
from .tg2 import (IngestionJournal, audit_export, generate_event, generate_queries,
                  export_cassandra_collection, ingest_resumable, workload_descriptor)


def sample_action(action: Callable[[], Any], interval: float = 2) -> tuple[dict[str, Any], Any]:
    started = time.monotonic()
    samples = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(action)
        while not future.done():
            containers = collect_containers("generated")
            gpu = collect_gpu()
            samples.append({
                "elapsed_seconds": time.monotonic() - started,
                "container_memory_bytes": sum(item["memory_bytes"] for item in containers),
                "container_cpu_percent": sum(item["cpu_percent"] for item in containers),
                "trustgraph_vram_bytes": gpu.get("attribution_memory_bytes", {}).get("trustgraph", 0),
                "asm_vram_bytes": gpu.get("attribution_memory_bytes", {}).get("asm", 0),
            })
            if not future.done():
                time.sleep(interval)
        result = future.result()
    if not samples:
        containers = collect_containers("generated")
        samples.append({"elapsed_seconds": time.monotonic() - started,
                        "container_memory_bytes": sum(item["memory_bytes"] for item in containers),
                        "container_cpu_percent": sum(item["cpu_percent"] for item in containers),
                        "trustgraph_vram_bytes": 0, "asm_vram_bytes": 0})
    return {
        "duration_seconds": time.monotonic() - started, "sample_count": len(samples), "samples": samples,
        "summary": {
            "container_memory_mean_bytes": statistics.fmean(item["container_memory_bytes"] for item in samples),
            "container_memory_peak_bytes": max(item["container_memory_bytes"] for item in samples),
            "container_cpu_mean_percent": statistics.fmean(item["container_cpu_percent"] for item in samples),
            "container_cpu_peak_percent": max(item["container_cpu_percent"] for item in samples),
            "trustgraph_vram_peak_bytes": max(item["trustgraph_vram_bytes"] for item in samples),
            "asm_vram_mean_bytes": statistics.fmean(item["asm_vram_bytes"] for item in samples),
        },
    }, result


def structured_query_audit(client: TrustGraphClient, event_count: int,
                           query_count: int = 100) -> dict[str, Any]:
    queries = generate_queries(event_count, count=min(query_count, event_count))
    latencies = []
    failures = []
    for query in queries:
        target = int(query["question"].split()[-1].rstrip("?"))
        subject = generate_event(target)["triples"][0]["s"]
        started = time.monotonic()
        rows = client.query_subject(subject)
        latencies.append(time.monotonic() - started)
        if len(rows) < 5:
            failures.append(query["query_id"])
    ordered = sorted(latencies)
    return {"valid": not failures, "query_count": len(queries), "failures": failures,
            "latency_seconds": {"mean": statistics.fmean(ordered),
                                "p50": ordered[len(ordered) // 2],
                                "p95": ordered[min(len(ordered) - 1, int(len(ordered) * .95))],
                                "max": ordered[-1]}}


class TG2Runner:
    def __init__(self, root: Path, token: str, run_id: str, event_count: int,
                 chunk_size: int, stabilization: float, resume: bool) -> None:
        self.root = root
        self.run_id = run_id
        self.event_count = event_count
        self.chunk_size = chunk_size
        self.resume = resume
        self.lifecycle = TG1Runner(root, token, stabilization, 30, 10, 8 * 1024**2)
        self.client = TrustGraphClient("http://localhost:8888/", token, flow_id=run_id,
                                       collection=run_id, timeout=120)
        self.raw = root / "results/raw"
        self.journals = root / "results/journals"
        self.journals.mkdir(parents=True, exist_ok=True)

    def run(self) -> dict[str, Any]:
        descriptor = workload_descriptor(self.event_count)
        if self.resume:
            self.lifecycle.command(self.lifecycle.compose + ["up", "-d"], timeout=180)
        else:
            self.lifecycle.fresh_stack()
        self.lifecycle.wait_ready()
        self.lifecycle.ensure_flow(self.client)
        stabilization = self.lifecycle.stabilize()
        before = snapshot(f"{self.run_id}-before", "empty")
        write_json(self.raw / f"{self.run_id}-before.json", before)
        journal = IngestionJournal(self.journals / f"{self.run_id}.json", descriptor["sha256"],
                                   self.event_count, self.chunk_size)
        ingestion_window, ingestion = sample_action(
            lambda: ingest_resumable(self.client, self.event_count, journal), interval=2)
        write_json(self.raw / f"{self.run_id}-ingestion-window.json", ingestion_window)
        time.sleep(30)
        after = snapshot(f"{self.run_id}-after", "post_ingest_idle")
        write_json(self.raw / f"{self.run_id}-after.json", after)
        resource_delta = delta(before, after, self.event_count)
        write_json(self.raw / f"{self.run_id}-delta.json", resource_delta)
        with tempfile.TemporaryDirectory(prefix="pmsb-tg2-audit-") as temporary:
            exporter = type("CollectionExport", (), {
                "export_triples": lambda _: export_cassandra_collection(self.run_id)
            })()
            exact_audit = audit_export(exporter, self.event_count, Path(temporary) / "audit.sqlite")
        query_audit = structured_query_audit(self.client, self.event_count)
        valid = stabilization["quiescent"] and exact_audit["valid"] and query_audit["valid"]
        manifest = {
            "schema_version": "tg2-checkpoint-run-v1", "run_id": self.run_id,
            "created_at": datetime.now(timezone.utc).isoformat(), "valid": valid,
            "checkpoint_events": self.event_count, "chunk_size": self.chunk_size,
            "resume": self.resume, "workload": descriptor, "stabilization": stabilization,
            "ingestion": ingestion, "ingestion_resources": ingestion_window["summary"],
            "ingestion_seconds": ingestion_window["duration_seconds"],
            "events_per_second": ingestion["imported_events"] / ingestion_window["duration_seconds"],
            "measurement_kind": "resume-validation" if self.resume else "fresh-checkpoint",
            "delta": resource_delta, "exact_export_audit": exact_audit,
            "structured_query_audit": query_audit,
        }
        write_json(self.raw / f"{self.run_id}-manifest.json", manifest)
        return manifest


def main() -> int:
    parser = argparse.ArgumentParser(prog="pmsb-tg2-run")
    parser.add_argument("--token", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--events", type=int, required=True, choices=[100, 1000, 10000, 100000, 1000000])
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--stabilization", type=float, default=60)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    runner = TG2Runner(Path.cwd(), args.token, args.run_id, args.events, args.chunk_size,
                       args.stabilization, args.resume)
    try:
        value = runner.run()
        print(json.dumps({"run_id": value["run_id"], "valid": value["valid"],
                          "events": value["checkpoint_events"],
                          "delta": value["delta"]["totals"],
                          "audit": value["exact_export_audit"]}, indent=2))
        return 0 if value["valid"] else 2
    finally:
        runner.lifecycle.stop_preserving_volumes()


if __name__ == "__main__":
    raise SystemExit(main())
