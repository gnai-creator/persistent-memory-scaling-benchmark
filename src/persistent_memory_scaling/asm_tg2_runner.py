"""Paired ASM-CM + Memory Bridge runner for the frozen TG-2 workload."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import struct
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .trustgraph.preflight import write_json
from .trustgraph.tg2 import TG2_SEED, generate_event, generate_queries, workload_descriptor


def canonical_event_content(event: dict[str, Any]) -> str:
    """Render exactly the frozen TG-2 event as the Bridge canonical payload."""
    return json.dumps(
        {
            "event_id": event["event_id"],
            "sequence": event["sequence"],
            "language": event["language"],
            "text": event["text"],
            "triples": event["triples"],
            "relevant_evidence_ids": event["relevant_evidence_ids"],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def snapshot_parts(payload: bytes) -> dict[str, int]:
    magic = b"ASMCMBRIDGE\x00"
    if not payload.startswith(magic):
        raise ValueError("unexpected ASM-CM snapshot format")
    offset = len(magic)
    header_size = struct.unpack(">I", payload[offset : offset + 4])[0]
    start = offset + 4
    header = json.loads(payload[start : start + header_size])
    neural = int(header["state_payload_bytes"])
    head = len(payload) - start - header_size - neural
    return {
        "snapshot_bytes": len(payload),
        "snapshot_header_bytes": header_size + offset + 4,
        "serialized_neural_state_bytes": neural,
        "serialized_retrieval_head_bytes": head,
    }


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def physical_store_bytes(path: Path) -> int:
    return sum(
        candidate.stat().st_size
        for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm"))
        if candidate.exists()
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, required=True)
    parser.add_argument("--queries", type=int, default=80)
    parser.add_argument("--seed", type=int, default=TG2_SEED)
    parser.add_argument("--repeat", type=int, required=True)
    parser.add_argument("--capacity", type=int, default=1024)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--asm-source-root", type=Path, required=True)
    parser.add_argument("--bridge-source-root", type=Path, required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.events < 1 or args.queries < 1 or args.repeat < 1:
        parser.error("events, queries and repeat must be positive")

    for source in (args.bridge_source_root, args.asm_source_root / "src"):
        resolved = str(source.resolve())
        if resolved not in sys.path:
            sys.path.insert(0, resolved)

    from asm_memory_bridge import ASMCMRuntime, MemoryQuery, MemoryWrite
    from asm_memory_bridge.retrieval.torch_head import TorchIDRetrievalHead
    from asm_memory_bridge.runtime.torch_backend import TorchASMCMBackend
    from asm_memory_bridge.stores import SQLitePayloadStore

    checkpoint_hash = hashlib.sha256(args.checkpoint.read_bytes()).hexdigest()
    artifact_hash = hashlib.sha256(args.artifact.read_bytes()).hexdigest()
    backend = TorchASMCMBackend(
        args.checkpoint.resolve(), asm_source_root=args.asm_source_root / "src", device=args.device
    )
    head = TorchIDRetrievalHead(
        backend,
        args.artifact,
        allowed_artifact_sha256={artifact_hash},
        checkpoint_sha256=checkpoint_hash,
        capacity=args.capacity,
        max_bytes=2048,
    )
    runtime = ASMCMRuntime(
        args.checkpoint,
        allowed_checkpoint_sha256={checkpoint_hash},
        backend=backend,
        retrieval_head=head,
    )

    namespace = f"tg2-{args.seed}"
    base_time = datetime(2026, 1, 1, tzinfo=UTC)
    args.database.parent.mkdir(parents=True, exist_ok=True)
    if args.database.exists():
        raise FileExistsError(f"refusing to reuse database: {args.database}")

    started_at = datetime.now(UTC).isoformat()
    with SQLitePayloadStore(args.database) as store:
        started = time.perf_counter()
        for index in range(args.events):
            event = generate_event(index, args.seed)
            memory = MemoryWrite(
                memory_id=event["event_id"],
                namespace_id=namespace,
                occurred_at=base_time + timedelta(microseconds=index),
                content=canonical_event_content(event),
                content_type="tg2-event-v1",
                source_id=event["relevant_evidence_ids"][0],
                authorization_labels=("public",),
                metadata={"sequence": str(index), "language": event["language"]},
            )
            store.put(memory)
            runtime.write(memory)
        ingestion_seconds = time.perf_counter() - started

        query_rows = []
        for query in generate_queries(args.events, args.seed, args.queries):
            memory_query = MemoryQuery(
                query_id=query["query_id"], namespace_id=namespace, requester_id=namespace,
                question=query["question"], asked_at=base_time + timedelta(days=1), top_k=5,
            )
            query_started = time.perf_counter()
            candidates = runtime.retrieve(memory_query)
            latency_ms = (time.perf_counter() - query_started) * 1000
            relevant = {item.replace("evidence", "event") for item in query["relevant_evidence_ids"]}
            retrieved = [candidate.memory_id for candidate in candidates]
            query_rows.append({
                "query_id": query["query_id"], "latency_ms": latency_ms,
                "retrieved_ids": retrieved, "recalled_at_5": bool(relevant.intersection(retrieved)),
            })

        metrics = runtime.state_metrics(namespace)
        snapshot = runtime.snapshot(namespace, payload_store_revision=store.revision)
        store_bytes = physical_store_bytes(args.database)

    latencies = [row["latency_ms"] for row in query_rows]
    result = {
        "schema_version": "asm-tg2-paired-run-v1",
        "started_at": started_at,
        "system": "ASM-CM + Memory Bridge 8.1",
        "protocol": {
            "workload": workload_descriptor(args.events, args.seed),
            "repeat": args.repeat, "query_count": args.queries, "top_k": 5,
            "capacity": args.capacity, "device": str(backend.device),
            "checkpoint": str(args.checkpoint.resolve()), "checkpoint_sha256": checkpoint_hash,
            "artifact": str(args.artifact.resolve()), "artifact_sha256": artifact_hash,
            "reader_included": False,
            "retrieval_note": "Phase 7.6 promoted head; fixed-capacity bindings over frozen ASM-CM",
        },
        "measurements": {
            "events": args.events,
            "ingestion_seconds": ingestion_seconds,
            "events_per_second": args.events / ingestion_seconds,
            "query_mean_ms": statistics.fmean(latencies),
            "query_p50_ms": percentile(latencies, .50),
            "query_p95_ms": percentile(latencies, .95),
            "recall_at_5": statistics.fmean(float(row["recalled_at_5"]) for row in query_rows),
            "payload_store_physical_bytes": store_bytes,
            "asm_neural_state_bytes": metrics.asm_neural_state_bytes,
            "retrieval_binding_bytes": metrics.retrieval_binding_bytes,
            "runtime_active_state_bytes": metrics.runtime_active_state_bytes,
            "binding_count": metrics.binding_count,
            "binding_capacity": metrics.binding_capacity,
            "eviction_count": metrics.eviction_count,
            **snapshot_parts(snapshot),
        },
        "queries": query_rows,
        "notes": [
            "This is a new paired TG-2 execution, not an inference from Phase 8.1.",
            "Reader latency and reader resources are excluded.",
            "Physical payload storage includes SQLite database, WAL and SHM files.",
            "The fixed binding capacity is part of the frozen run configuration; evictions are reported.",
        ],
    }
    write_json(args.output, result)
    print(json.dumps({"output": str(args.output), "measurements": result["measurements"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
