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
from .metrics import (collect_containers, collect_gpu, delta, matched_delta, snapshot,
                      summarize_observations)
from .preflight import write_json
from .tg1_runner import TG1Runner, validate_cycle
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


def aggregate_tg2_cycles(manifests: list[dict[str, Any]]) -> dict[str, Any]:
    if len(manifests) < 2 or any(not item.get("valid") for item in manifests):
        raise ValueError("TG-2 aggregate requires at least two valid cycles")
    checkpoints = {item["checkpoint_events"] for item in manifests}
    fingerprints = {item["workload"]["sha256"] for item in manifests}
    if len(checkpoints) != 1 or len(fingerprints) != 1:
        raise ValueError("TG-2 cycles must share checkpoint and workload fingerprint")
    metrics = {}
    extractors = {
        "matched_container_memory_bytes": lambda item: item["matched_delta"]["totals"]["container_memory_bytes"],
        "matched_volume_physical_bytes": lambda item: item["matched_delta"]["totals"]["volume_physical_bytes"],
        "ingestion_seconds": lambda item: item["ingestion_seconds"],
        "events_per_second": lambda item: item["events_per_second"],
        "structured_query_mean_seconds": lambda item: item["structured_query_audit"]["latency_seconds"]["mean"],
        "structured_query_p95_seconds": lambda item: item["structured_query_audit"]["latency_seconds"]["p95"],
        "loaded_memory_peak_bytes": lambda item: item["ingestion_resources"]["container_memory_peak_bytes"],
        "trustgraph_vram_peak_bytes": lambda item: item["ingestion_resources"]["gpu_attribution"]["trustgraph"]["peak_bytes"],
    }
    if all("_loaded_window" in item for item in manifests):
        extractors["loaded_cpu_mean_percent"] = lambda item: statistics.fmean(
            sample["container_cpu_percent"] for sample in item["_loaded_window"]["samples"])
        extractors["loaded_cpu_peak_percent"] = lambda item: max(
            sample["container_cpu_percent"] for sample in item["_loaded_window"]["samples"])
    for name, extract in extractors.items():
        metrics[name] = summarize_observations([float(extract(item)) for item in manifests])
    return {"schema_version": "tg2-checkpoint-aggregate-v1",
            "checkpoint_events": checkpoints.pop(), "workload_sha256": fingerprints.pop(),
            "run_ids": [item["run_id"] for item in manifests], "repetitions": len(manifests),
            "confidence_method": "two-sided Student t approximation", "metrics": metrics}


class TG2Runner:
    def __init__(self, root: Path, token: str, run_id: str, event_count: int,
                 chunk_size: int, stabilization: float, phase_duration: float,
                 resume: bool) -> None:
        self.root = root
        self.run_id = run_id
        self.event_count = event_count
        self.chunk_size = chunk_size
        self.resume = resume
        self.phase_duration = phase_duration
        self.lifecycle = TG1Runner(root, token, stabilization, phase_duration, 10, 8 * 1024**2)
        self.client = TrustGraphClient("http://localhost:8888/", token, flow_id=run_id,
                                       collection=run_id, timeout=120)
        self.raw = root / "results/raw"
        self.journals = root / "results/journals"
        self.journals.mkdir(parents=True, exist_ok=True)

    def audit(self) -> dict[str, int | bool]:
        with tempfile.TemporaryDirectory(prefix="pmsb-tg2-audit-") as temporary:
            exporter = type("CollectionExport", (), {
                "export_triples": lambda _: export_cassandra_collection(self.run_id)
            })()
            return audit_export(exporter, self.event_count, Path(temporary) / "audit.sqlite")

    def run_resume(self, descriptor: dict[str, Any], stabilization: dict[str, Any],
                   journal: IngestionJournal) -> dict[str, Any]:
        before = snapshot(f"{self.run_id}-before", "empty")
        ingestion_window, ingestion = sample_action(
            lambda: ingest_resumable(self.client, self.event_count, journal), interval=2)
        after = snapshot(f"{self.run_id}-after", "post_ingest_idle")
        resource_delta = delta(before, after, self.event_count)
        exact_audit = self.audit()
        query_audit = structured_query_audit(self.client, self.event_count)
        return {
            "schema_version": "tg2-checkpoint-run-v2", "run_id": self.run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "valid": stabilization["quiescent"] and exact_audit["valid"] and query_audit["valid"],
            "rejection_reasons": [], "checkpoint_events": self.event_count,
            "chunk_size": self.chunk_size, "resume": True, "workload": descriptor,
            "stabilization": stabilization, "ingestion": ingestion,
            "ingestion_resources": ingestion_window["summary"],
            "ingestion_seconds": ingestion_window["duration_seconds"],
            "events_per_second": ingestion["imported_events"] / ingestion_window["duration_seconds"],
            "measurement_kind": "resume-validation", "delta": resource_delta,
            "exact_export_audit": exact_audit, "structured_query_audit": query_audit,
        }

    def run(self) -> dict[str, Any]:
        descriptor = workload_descriptor(self.event_count)
        if self.resume:
            self.lifecycle.command(self.lifecycle.compose + ["up", "-d"], timeout=180)
        else:
            self.lifecycle.fresh_stack()
        self.lifecycle.wait_ready()
        self.lifecycle.ensure_flow(self.client)
        stabilization = self.lifecycle.stabilize()
        journal = IngestionJournal(self.journals / f"{self.run_id}.json", descriptor["sha256"],
                                   self.event_count, self.chunk_size)
        if self.resume:
            manifest = self.run_resume(descriptor, stabilization, journal)
            write_json(self.raw / f"{self.run_id}-manifest.json", manifest)
            return manifest

        baseline = snapshot(f"{self.run_id}-empty-start", "empty")
        write_json(self.raw / f"{self.run_id}-empty-start.json", baseline)
        empty_window, _ = self.lifecycle.measured_window(
            self.run_id, "empty-control", self.phase_duration)
        empty_end = snapshot(f"{self.run_id}-empty-end", "empty")
        write_json(self.raw / f"{self.run_id}-empty-end.json", empty_end)

        def ingest() -> dict[str, Any]:
            started = time.monotonic()
            result = ingest_resumable(self.client, self.event_count, journal)
            result["action_seconds"] = time.monotonic() - started
            return result

        loaded_window, ingestion = self.lifecycle.measured_window(
            self.run_id, "loaded", self.phase_duration, ingest)
        after = snapshot(f"{self.run_id}-loaded-end", "post_ingest_idle")
        write_json(self.raw / f"{self.run_id}-loaded-end.json", after)
        control_delta = delta(baseline, empty_end, self.event_count)
        loaded_delta = delta(empty_end, after, self.event_count)
        adjusted = matched_delta(control_delta, loaded_delta)
        write_json(self.raw / f"{self.run_id}-matched-delta.json", adjusted)
        exact_audit = self.audit()
        query_audit = structured_query_audit(self.client, self.event_count)
        container_sets = [{item["container_id"] for item in value["containers"]}
                          for value in (baseline, empty_end, after)]
        reasons = validate_cycle(control_delta, container_sets, 8 * 1024**2)
        if not stabilization["quiescent"]:
            reasons.append("pre_baseline_disk_not_quiescent")
        if ingestion["action_seconds"] > self.phase_duration:
            reasons.append("ingestion_exceeded_matched_window")
        if not exact_audit["valid"]:
            reasons.append("exact_export_audit_failed")
        if not query_audit["valid"]:
            reasons.append("structured_query_audit_failed")
        manifest = {
            "schema_version": "tg2-checkpoint-run-v2", "run_id": self.run_id,
            "created_at": datetime.now(timezone.utc).isoformat(), "valid": not reasons,
            "rejection_reasons": reasons,
            "checkpoint_events": self.event_count, "chunk_size": self.chunk_size,
            "resume": self.resume, "workload": descriptor, "stabilization": stabilization,
            "phase_duration_seconds": self.phase_duration,
            "ingestion": ingestion, "ingestion_resources": loaded_window["summary"],
            "empty_resources": empty_window["summary"],
            "ingestion_seconds": ingestion["action_seconds"],
            "events_per_second": ingestion["imported_events"] / ingestion["action_seconds"],
            "measurement_kind": "official-paired-fresh",
            "control_delta": control_delta, "loaded_delta": loaded_delta,
            "matched_delta": adjusted, "exact_export_audit": exact_audit,
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
    parser.add_argument("--phase-duration", type=float, default=30)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    runner = TG2Runner(Path.cwd(), args.token, args.run_id, args.events, args.chunk_size,
                       args.stabilization, args.phase_duration, args.resume)
    try:
        value = runner.run()
        print(json.dumps({"run_id": value["run_id"], "valid": value["valid"],
                          "events": value["checkpoint_events"],
                          "delta": value.get("matched_delta", value.get("delta"))["totals"],
                          "audit": value["exact_export_audit"]}, indent=2))
        return 0 if value["valid"] else 2
    finally:
        runner.lifecycle.stop_preserving_volumes()


if __name__ == "__main__":
    raise SystemExit(main())
