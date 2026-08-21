"""Run cumulative ASM Memory Bridge reader-context scaling with a local Ollama reader."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .asm_tg2_runner import canonical_event_content, physical_store_bytes, snapshot_parts
from .reader_context_scaling import aggregate, render
from .trustgraph.tg2 import TG2_SEED, generate_event, generate_queries


def parse_checkpoints(value: str) -> list[int]:
    try:
        checkpoints = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("checkpoints must be comma-separated integers") from exc
    if not checkpoints or any(item <= 0 for item in checkpoints):
        raise argparse.ArgumentTypeError("checkpoints must be positive")
    if checkpoints != sorted(set(checkpoints)):
        raise argparse.ArgumentTypeError("checkpoints must be unique and increasing")
    return checkpoints


def answer_quality(answer: str, expected: str, abstained: bool) -> float:
    """Synthetic TG-2 QA: normalized expected value must occur in a grounded answer."""
    if abstained:
        return 0.0
    normalized_answer = " ".join(answer.casefold().split())
    normalized_expected = " ".join(expected.casefold().split())
    return float(bool(normalized_expected) and normalized_expected in normalized_answer)


def call_reader_measured(reader: Any, query: Any, package: Any, ReaderError: type[Exception]) -> dict[str, Any]:
    """Count every Ollama attempt and fail closed while preserving measured consumption."""
    transport = reader._transport
    responses: list[dict[str, Any]] = []

    def capturing_transport(payload: dict[str, Any]) -> dict[str, Any]:
        response = transport(payload)
        responses.append(response)
        return response

    reader._transport = capturing_transport
    started = time.perf_counter()
    try:
        answer = reader.answer(query, package)
        failure = ""
    except ReaderError as exc:
        answer = None
        failure = str(exc)
    finally:
        reader._transport = transport
    input_tokens = sum(int(response.get("prompt_eval_count", 0) or 0) for response in responses)
    output_tokens = sum(int(response.get("eval_count", 0) or 0) for response in responses)
    if input_tokens <= 0:
        raise RuntimeError("Ollama did not report a positive prompt_eval_count")
    return {
        "answer": "" if answer is None else answer.answer,
        "cited_ids": [] if answer is None else list(answer.cited_memory_ids),
        "abstained": True if answer is None else answer.abstained,
        "reader_model": f"ollama:{reader.model}" if answer is None else answer.reader_model,
        "latency_ms": (time.perf_counter() - started) * 1000,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "attempts": len(responses),
        "contract_failure": bool(failure),
        "failure_error": failure,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _write_json(path: Path, value: Any) -> None:
    _write_atomic(path, (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode())


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{number}") from exc
    return rows


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _memory(event: dict[str, Any], namespace: str, base_time: datetime, MemoryWrite: Any) -> Any:
    index = int(event["sequence"])
    return MemoryWrite(
        memory_id=event["event_id"],
        namespace_id=namespace,
        occurred_at=base_time + timedelta(microseconds=index),
        content=canonical_event_content(event),
        content_type="tg2-event-v1",
        source_id=event["relevant_evidence_ids"][0],
        authorization_labels=("public",),
        metadata={"sequence": str(index), "language": event["language"]},
    )


def _evidence_package(candidates: tuple[Any, ...], store: Any, namespace: str,
                      query_id: str, Evidence: Any, EvidencePackage: Any) -> Any:
    evidence = []
    for candidate in candidates:
        memory = store.get(namespace, candidate.memory_id)
        if memory is None:
            raise RuntimeError(f"retrieved payload is missing: {candidate.memory_id}")
        evidence.append(Evidence(
            memory_id=memory.memory_id,
            occurred_at=memory.occurred_at,
            content=memory.content,
            source_id=memory.source_id,
            score=candidate.score,
        ))
    context_bytes = sum(len(item.content.encode("utf-8")) for item in evidence)
    return EvidencePackage(
        query_id=query_id,
        evidence=tuple(evidence),
        omitted_candidates=0,
        context_bytes=context_bytes,
        provenance_complete=True,
        payload_store_revision=store.revision,
        policy_version="pmsb-tg2-local-reader-v1",
    )


def _load_reader_config(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("provider") != "ollama" or not value.get("local_only"):
        raise ValueError("reader config must declare local Ollama")
    generation = value.get("generation", {})
    required = ("temperature", "seed", "num_ctx", "max_new_tokens", "think")
    if any(key not in generation for key in required):
        raise ValueError("reader config is missing frozen generation fields")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoints", type=parse_checkpoints, default=parse_checkpoints("10000,100000,1000000"))
    parser.add_argument("--queries", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=TG2_SEED)
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--capacity", type=int, default=1024)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--asm-source-root", type=Path, required=True)
    parser.add_argument("--bridge-source-root", type=Path, required=True)
    parser.add_argument("--reader-config", type=Path, required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if args.queries < 1 or args.chunk_size < 1 or args.capacity < 1:
        parser.error("queries, chunk-size and capacity must be positive")

    for source in (args.bridge_source_root / "src", args.asm_source_root / "src"):
        resolved = str(source.resolve())
        if resolved not in sys.path:
            sys.path.insert(0, resolved)

    from asm_memory_bridge import ASMCMRuntime, Evidence, EvidencePackage, MemoryQuery, MemoryWrite
    from asm_memory_bridge.errors import ReaderError
    from asm_memory_bridge.readers.ollama import OllamaReader
    from asm_memory_bridge.retrieval.torch_head import TorchIDRetrievalHead
    from asm_memory_bridge.runtime.torch_backend import TorchASMCMBackend
    from asm_memory_bridge.stores import SQLitePayloadStore

    reader_config = _load_reader_config(args.reader_config)
    generation = reader_config["generation"]
    checkpoint_hash, artifact_hash = _sha256(args.checkpoint), _sha256(args.artifact)
    backend = TorchASMCMBackend(
        args.checkpoint.resolve(), asm_source_root=args.asm_source_root / "src", device=args.device
    )
    head = TorchIDRetrievalHead(
        backend, args.artifact, allowed_artifact_sha256={artifact_hash},
        checkpoint_sha256=checkpoint_hash, capacity=args.capacity, max_bytes=2048,
    )
    runtime = ASMCMRuntime(
        args.checkpoint, allowed_checkpoint_sha256={checkpoint_hash}, backend=backend,
        retrieval_head=head,
    )
    reader = OllamaReader(
        model=reader_config["model"], base_url=reader_config["base_url"],
        temperature=float(generation["temperature"]), seed=int(generation["seed"]),
        num_ctx=int(generation["num_ctx"]), max_new_tokens=int(generation["max_new_tokens"]),
        think=bool(generation["think"]), attempts=int(generation.get("attempts", 2)),
        retry_delay_seconds=float(generation.get("retry_delay_seconds", 1)),
        timeout_seconds=float(generation.get("timeout_seconds", 120)),
    )

    args.output_root.mkdir(parents=True, exist_ok=True)
    database = args.output_root / "payloads.sqlite3"
    snapshot_path = args.output_root / "runtime.snapshot"
    state_path = args.output_root / "state.json"
    rows_path = args.output_root / "reader-context.jsonl"
    summary_path = args.output_root / "summary.json"
    manifest_path = args.output_root / "manifest.json"
    png_path = args.output_root / "reader-context-scaling.png"
    svg_path = args.output_root / "reader-context-scaling.svg"
    namespace = f"tg2-reader-scaling-{args.seed}"
    base_time = datetime(2026, 1, 1, tzinfo=UTC)

    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {
        "schema_version": "asm-reader-scaling-state-v1", "ingested_events": 0,
        "snapshot_store_revision": 0, "completed_checkpoints": [], "checkpoint_resources": {},
    }
    frozen = {
        "checkpoints": args.checkpoints, "queries": args.queries, "seed": args.seed,
        "capacity": args.capacity, "checkpoint_sha256": checkpoint_hash,
        "artifact_sha256": artifact_hash, "reader_config_sha256": _sha256(args.reader_config),
    }
    if "frozen" in state and state["frozen"] != frozen:
        raise ValueError("existing output state belongs to a different frozen protocol")
    state["frozen"] = frozen

    query_specs = generate_queries(args.checkpoints[0], args.seed, args.queries)
    rows = _load_jsonl(rows_path)
    completed_rows = {(int(row["history_events"]), str(row["query_id"])) for row in rows}
    checkpoint_resources: dict[str, Any] = dict(state.get("checkpoint_resources", {}))

    with SQLitePayloadStore(database) as store:
        if snapshot_path.exists():
            runtime.restore(
                namespace, snapshot_path.read_bytes(),
                expected_payload_store_revision=int(state["snapshot_store_revision"]),
            )
            # A crash can commit SQLite rows after the last atomic snapshot. Replaying
            # the store is idempotent and repairs that narrow gap before continuing.
            for memory in store.list_namespace(namespace):
                runtime.write(memory)
            if store.revision != int(state["snapshot_store_revision"]):
                snapshot = runtime.snapshot(namespace, payload_store_revision=store.revision)
                _write_atomic(snapshot_path, snapshot)
                state["snapshot_store_revision"] = store.revision
                state["ingested_events"] = len(store.list_namespace(namespace))
                _write_json(state_path, state)
        elif store.revision:
            # The first process may have stopped before publishing its initial
            # snapshot. Rebuild deterministically from the canonical store.
            for memory in store.list_namespace(namespace):
                runtime.write(memory)
            snapshot = runtime.snapshot(namespace, payload_store_revision=store.revision)
            _write_atomic(snapshot_path, snapshot)
            state["snapshot_store_revision"] = store.revision
            state["ingested_events"] = len(store.list_namespace(namespace))
            _write_json(state_path, state)

        for checkpoint in args.checkpoints:
            completed_checkpoints = set(int(item) for item in state["completed_checkpoints"])
            checkpoint_row_count = sum(1 for item in rows if int(item["history_events"]) == checkpoint)
            if checkpoint in completed_checkpoints:
                if checkpoint_row_count != args.queries or str(checkpoint) not in checkpoint_resources:
                    raise ValueError(f"checkpoint {checkpoint} is marked complete but its artifacts are incomplete")
                continue
            ingested = int(state["ingested_events"])
            if ingested > checkpoint:
                raise ValueError(
                    f"cannot evaluate incomplete checkpoint {checkpoint} after ingesting {ingested} events"
                )
            while ingested < checkpoint:
                end = min(checkpoint, ingested + args.chunk_size)
                started = time.perf_counter()
                for index in range(ingested, end):
                    memory = _memory(generate_event(index, args.seed), namespace, base_time, MemoryWrite)
                    store.put(memory)
                    runtime.write(memory)
                elapsed = time.perf_counter() - started
                snapshot = runtime.snapshot(namespace, payload_store_revision=store.revision)
                _write_atomic(snapshot_path, snapshot)
                ingested = end
                state.update({"ingested_events": ingested, "snapshot_store_revision": store.revision})
                _write_json(state_path, state)
                print(json.dumps({"phase": "ingest", "events": ingested, "chunk_seconds": elapsed}), flush=True)

            for spec in query_specs:
                key = (checkpoint, spec["query_id"])
                if key in completed_rows:
                    continue
                query = MemoryQuery(
                    query_id=f"{spec['query_id']}-at-{checkpoint}", namespace_id=namespace,
                    requester_id=namespace, question=spec["question"],
                    asked_at=base_time + timedelta(days=1), top_k=5,
                )
                retrieval_started = time.perf_counter()
                candidates = runtime.retrieve(query)
                retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
                package = _evidence_package(candidates, store, namespace, query.query_id, Evidence, EvidencePackage)
                answer = call_reader_measured(reader, query, package, ReaderError)
                expected_ids = {item.replace("evidence", "event") for item in spec["relevant_evidence_ids"]}
                retrieved_ids = [item.memory_id for item in candidates]
                row = {
                    "system": "ASM Memory Bridge", "history_events": checkpoint,
                    "query_id": spec["query_id"], "question": spec["question"],
                    "expected_answer": spec["expected_answer"],
                    "reader_context_tokens": answer["input_tokens"],
                    "reader_output_tokens": answer["output_tokens"],
                    "recall_at_5": float(bool(expected_ids.intersection(retrieved_ids))),
                    "qa_score": answer_quality(answer["answer"], spec["expected_answer"], answer["abstained"]),
                    "retrieved_ids": retrieved_ids, "cited_ids": answer["cited_ids"],
                    "answer": answer["answer"], "abstained": answer["abstained"],
                    "retrieval_latency_ms": retrieval_ms, "reader_latency_ms": answer["latency_ms"],
                    "evidence_bytes": package.context_bytes, "reader_model": answer["reader_model"],
                    "reader_attempts": answer["attempts"],
                    "reader_contract_failure": answer["contract_failure"],
                    "reader_failure_error": answer["failure_error"],
                }
                _append_jsonl(rows_path, row)
                rows.append(row)
                completed_rows.add(key)
                print(json.dumps({"phase": "query", "checkpoint": checkpoint,
                                  "completed": sum(1 for item in rows if item["history_events"] == checkpoint),
                                  "total": args.queries}), flush=True)

            metrics = runtime.state_metrics(namespace)
            snapshot = runtime.snapshot(namespace, payload_store_revision=store.revision)
            checkpoint_resources[str(checkpoint)] = {
                "payload_store_physical_bytes": physical_store_bytes(database),
                "asm_neural_state_bytes": metrics.asm_neural_state_bytes,
                "retrieval_binding_bytes": metrics.retrieval_binding_bytes,
                "runtime_active_state_bytes": metrics.runtime_active_state_bytes,
                "binding_count": metrics.binding_count, "binding_capacity": metrics.binding_capacity,
                "eviction_count": metrics.eviction_count, **snapshot_parts(snapshot),
            }
            completed = set(int(item) for item in state["completed_checkpoints"])
            completed.add(checkpoint)
            state["completed_checkpoints"] = sorted(completed)
            state["checkpoint_resources"] = checkpoint_resources
            _write_json(state_path, state)

    result = aggregate(rows)
    result["protocol"] = frozen
    result["reader"] = reader_config
    result["resources"] = checkpoint_resources
    result["quality_metric"] = "case-insensitive containment of the frozen TG-2 expected value"
    _write_json(summary_path, result)
    render(result, png_path, svg_path)
    _write_json(manifest_path, {
        "schema_version": "asm-reader-context-scaling-manifest-v1",
        "status": "complete", "created_at": datetime.now(UTC).isoformat(),
        "artifacts": {path.name: _sha256(path) for path in (rows_path, summary_path, png_path, svg_path)},
        "source": {"checkpoint": str(args.checkpoint.resolve()), "artifact": str(args.artifact.resolve()),
                   "reader_config": str(args.reader_config.resolve())},
    })
    print(json.dumps({"status": "complete", "output_root": str(args.output_root)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
