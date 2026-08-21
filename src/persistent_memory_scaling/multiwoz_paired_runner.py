"""Run ASM Memory Bridge vs lexical RAG on MultiWOZ with cumulative distractors."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .asm_reader_context_scaling_runner import (
    _append_jsonl,
    _evidence_package,
    _load_jsonl,
    _load_reader_config,
    _sha256,
    _write_atomic,
    _write_json,
    call_reader_measured,
)
from .asm_tg2_runner import physical_store_bytes, snapshot_parts
from .multiwoz_distractors import (
    Document,
    Workload,
    load_workload,
    parse_distractor_checkpoints,
    workload_sha256,
)
from .rag_reader_context_scaling_runner import fts_query
from .reader_context_scaling import aggregate, render

QUALITY_RECALL_FLOOR = 0.90
QUALITY_QA_FLOOR = 0.65


def parse_top_k_values(value: str) -> list[int]:
    try:
        values = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise ValueError("top-k values must be comma-separated integers") from exc
    if not values or any(item < 1 for item in values):
        raise ValueError("top-k values must be positive")
    if values != sorted(set(values)):
        raise ValueError("top-k values must be unique and increasing")
    return values


def aggregate_sweep(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate each top-k independently instead of pooling different budgets."""
    points: list[dict[str, Any]] = []
    for top_k in sorted({int(row["top_k"]) for row in rows}):
        selected = [row for row in rows if int(row["top_k"]) == top_k]
        for point in aggregate(selected)["points"]:
            points.append({**point, "top_k": top_k})
    return {
        "schema_version": "reader-context-top-k-sweep-summary-v1",
        "measurement_status": "measured",
        "points": points,
    }


def quality_frontier(
    sweep: dict[str, Any], *, recall_floor: float, qa_floor: float
) -> dict[str, Any]:
    """Select the smallest predeclared K meeting both quality floors."""
    systems = sorted({str(point["system"]) for point in sweep["points"]})
    histories = sorted({int(point["history_events"]) for point in sweep["points"]})
    selected_points: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    for history in histories:
        chosen_for_history: list[dict[str, Any]] = []
        for system in systems:
            candidates = sorted(
                (point for point in sweep["points"]
                 if point["system"] == system and int(point["history_events"]) == history),
                key=lambda point: int(point["top_k"]),
            )
            eligible = [point for point in candidates
                        if point["recall_at_5"] >= recall_floor and point["qa_score"] >= qa_floor]
            chosen = eligible[0] if eligible else None
            decisions.append({
                "system": system, "history_events": history,
                "quality_target_met": chosen is not None,
                "selected_top_k": None if chosen is None else chosen["top_k"],
            })
            if chosen is not None:
                chosen_for_history.append(chosen)
        authorized = len(chosen_for_history) == len(systems)
        for decision in decisions:
            if int(decision["history_events"]) == history:
                decision["cross_system_comparison_authorized"] = authorized
        if authorized:
            selected_points.extend(chosen_for_history)
    return {
        "schema_version": "reader-context-quality-frontier-v1",
        "measurement_status": "measured",
        "recall_label": "Recall@selected-K",
        "quality_floor": {"recall": recall_floor, "qa": qa_floor},
        "points": selected_points,
        "decisions": decisions,
        "interpretation_gate": "Context is comparable only where every reported system met both frozen floors.",
    }


def render_quality_frontier(summary: dict[str, Any], png: Path, svg: Path) -> None:
    """Render eligible points or an explicit no-quality-match result."""
    if summary["points"]:
        render(summary, png, svg)
        return
    import os
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/pmsb-matplotlib")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure, axis = plt.subplots(figsize=(12, 6))
    figure.patch.set_facecolor("#111318")
    axis.set_facecolor("#111318")
    axis.axis("off")
    axis.text(.5, .62, "NO QUALITY-MATCHED COMPARISON", ha="center", va="center",
              color="white", fontsize=22, weight="bold")
    floors = summary["quality_floor"]
    axis.text(.5, .45,
              f"No history checkpoint had all systems reach Recall ≥ {floors['recall']:.0%} "
              f"and QA ≥ {floors['qa']:.0%}.",
              ha="center", va="center", color="#ffca5c", fontsize=14)
    axis.text(.5, .32, "See top-k-sweep-summary.json for all measured operating points.",
              ha="center", va="center", color="#c0caf5", fontsize=12)
    png.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(png, dpi=180, bbox_inches="tight")
    figure.savefig(svg, bbox_inches="tight")
    plt.close(figure)


def render_top_k_sweep(summary: dict[str, Any], png: Path, svg: Path) -> None:
    """Render every measured K without implying that the quality gate passed."""
    import os
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/pmsb-matplotlib")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    points = summary["points"]
    plt.style.use("dark_background")
    systems = [
        "ASM Memory Bridge",
        "ASM Memory Bridge (compact)",
        "RAG (SQLite FTS5/BM25)",
    ]
    labels = ["ASM full", "ASM compact", "RAG BM25"]
    histories = sorted({int(point["history_events"]) for point in points})
    colors = ("#55d6be", "#ffca5c", "#7aa2f7")
    figure, axes = plt.subplots(3, 3, figsize=(18, 14), constrained_layout=True)
    figure.patch.set_facecolor("#111318")
    figure.suptitle(
        "MultiWOZ controlled distractors — measured top-k sweep\n"
        "No checkpoint passed the cross-system quality gate (Recall ≥ 90%, QA ≥ 70%)",
        color="white", fontsize=18, weight="bold",
    )
    for row_index, (system, label) in enumerate(zip(systems, labels, strict=True)):
        for history, color in zip(histories, colors, strict=False):
            selected = sorted(
                (point for point in points
                 if point["system"] == system and int(point["history_events"]) == history),
                key=lambda point: int(point["top_k"]),
            )
            top_k = [int(point["top_k"]) for point in selected]
            distractors = history - int(summary["protocol"]["base_history_documents"])
            curve_label = f"{distractors:,} distractors"
            axes[row_index, 0].plot(
                top_k, [point["context_tokens"]["p95"] for point in selected],
                "o-", color=color, linewidth=2, label=curve_label,
            )
            axes[row_index, 1].plot(
                top_k, [100 * point["recall_at_5"] for point in selected],
                "o-", color=color, linewidth=2, label=curve_label,
            )
            axes[row_index, 2].plot(
                top_k, [100 * point["qa_score"] for point in selected],
                "o-", color=color, linewidth=2, label=curve_label,
            )
        axes[row_index, 0].set_ylabel(f"{label}\nReader tokens (p95)")
        axes[row_index, 1].set_ylabel(f"{label}\nRecall@K (%)")
        axes[row_index, 2].set_ylabel(f"{label}\nQA (%)")
        axes[row_index, 1].axhline(90, color="#f7768e", linestyle="--", alpha=.85,
                                   label="Recall floor 90%")
        axes[row_index, 2].axhline(70, color="#f7768e", linestyle="--", alpha=.85,
                                   label="QA floor 70%")
        for column in range(3):
            axis = axes[row_index, column]
            axis.set_facecolor("#111318")
            axis.set_xticks(sorted({int(point["top_k"]) for point in points}))
            axis.set_xlabel("Retrieved documents (K)")
            axis.grid(alpha=.2)
            axis.legend(fontsize=8)
        axes[row_index, 1].set_ylim(0, 105)
        axes[row_index, 2].set_ylim(0, 105)
    axes[0, 0].set_title("Context cost")
    axes[0, 1].set_title("Retrieval quality")
    axes[0, 2].set_title("Answer quality")
    png.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(png, dpi=180, facecolor=figure.get_facecolor())
    figure.savefig(svg, facecolor=figure.get_facecolor())
    plt.close(figure)


def multiwoz_answer_quality(answer: str, expected: str, abstained: bool) -> float:
    """Score supported slot answers by containment of any annotated slot value."""
    if abstained:
        return 0.0
    normalized_answer = " ".join(answer.casefold().split())
    values = (" ".join(item.casefold().split()) for item in expected.split(","))
    return float(any(value and value in normalized_answer for value in values))


def _reader(config: dict[str, Any], OllamaReader: Any) -> Any:
    generation = config["generation"]
    return OllamaReader(
        model=config["model"],
        base_url=config["base_url"],
        temperature=float(generation["temperature"]),
        seed=int(generation["seed"]),
        num_ctx=int(generation["num_ctx"]),
        max_new_tokens=int(generation["max_new_tokens"]),
        think=bool(generation["think"]),
        attempts=int(generation.get("attempts", 2)),
        retry_delay_seconds=float(generation.get("retry_delay_seconds", 1)),
        timeout_seconds=float(generation.get("timeout_seconds", 180)),
    )


def _memory(document: Document, index: int, namespace: str, MemoryWrite: Any) -> Any:
    return MemoryWrite(
        memory_id=document.memory_id,
        namespace_id=namespace,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=index),
        content=document.content,
        content_type="multiwoz-dialogue-v2.2",
        source_id=document.source_id,
        authorization_labels=("public", "commercial-compatible:mit"),
        metadata={"dataset": "MultiWOZ 2.2", "controlled_distractor": index >= 0},
    )


def _protocol(
    args: argparse.Namespace, workload: Workload, config: dict[str, Any]
) -> dict[str, Any]:
    base_count = len(workload.base_documents)
    return {
        "schema_version": "multiwoz-distractor-scaling-v1",
        "dataset": "MultiWOZ 2.2",
        "dataset_sha256": workload.dataset_sha256,
        "workload_sha256": workload_sha256(workload),
        "evaluation_question_ids": list(workload.evaluation_ids),
        "queries": len(workload.queries),
        "base_history_documents": base_count,
        "distractor_checkpoints": args.distractors,
        "history_document_checkpoints": [base_count + item for item in args.distractors],
        "distractor_source": "MultiWOZ 2.2 train dialogues in deterministic corpus order",
        "top_k_values": args.top_k_values,
        "quality_target": {
            "recall": args.quality_recall_floor,
            "qa": args.quality_qa_floor,
            "selection": "smallest predeclared top_k satisfying both floors",
        },
        "capacity": args.capacity,
        "asm_compactor": {
            "kind": "query-conditioned-extractive-windows-v2",
            "max_total_bytes": args.compact_max_total_bytes,
            "max_bytes_per_memory": args.compact_max_bytes_per_memory,
            "max_anchors_per_memory": args.compact_max_anchors_per_memory,
            "window_radius": args.compact_window_radius,
            "answer_or_gold_visible_to_compactor": False,
        },
        "reader_config_sha256": _sha256(args.reader_config),
        "reader": f"ollama:{config['model']}",
        "same_documents_queries_reader_top_k": True,
    }


def _row(
    *, system: str, history_events: int, distractors: int, spec: Any,
    top_k: int, retrieved_ids: list[str], evidence: Any, answer: dict[str, Any],
    retrieval_ms: float,
) -> dict[str, Any]:
    relevant = set(spec.relevant_memory_ids)
    return {
        "system": system,
        "history_events": history_events,
        "distractor_count": distractors,
        "top_k": top_k,
        "query_id": spec.query_id,
        "question": spec.question,
        "expected_answer": spec.expected_answer,
        "relevant_memory_ids": list(spec.relevant_memory_ids),
        "reader_context_tokens": answer["input_tokens"],
        "reader_output_tokens": answer["output_tokens"],
        "recall_at_5": float(bool(relevant.intersection(retrieved_ids))),
        "qa_score": multiwoz_answer_quality(
            answer["answer"], spec.expected_answer, answer["abstained"]
        ),
        "retrieved_ids": retrieved_ids,
        "cited_ids": answer["cited_ids"],
        "answer": answer["answer"],
        "abstained": answer["abstained"],
        "retrieval_latency_ms": retrieval_ms,
        "reader_latency_ms": answer["latency_ms"],
        "evidence_bytes": evidence.context_bytes,
        "reader_model": answer["reader_model"],
        "reader_attempts": answer["attempts"],
        "reader_contract_failure": answer["contract_failure"],
        "reader_failure_error": answer["failure_error"],
    }


def run_asm(args: argparse.Namespace, workload: Workload, protocol: dict[str, Any], api: dict[str, Any]) -> None:
    root = args.output_root / "asm"
    root.mkdir(parents=True, exist_ok=True)
    database, snapshot_path = root / "payloads.sqlite3", root / "runtime.snapshot"
    state_path, rows_path = root / "state.json", root / "reader-context.jsonl"
    checkpoint_hash, artifact_hash = _sha256(args.checkpoint), _sha256(args.artifact)
    backend = api["TorchASMCMBackend"](
        args.checkpoint.resolve(), asm_source_root=args.asm_source_root / "src", device=args.device
    )
    head = api["TorchIDRetrievalHead"](
        backend, args.artifact, allowed_artifact_sha256={artifact_hash},
        checkpoint_sha256=checkpoint_hash, capacity=args.capacity, max_bytes=2048,
    )
    runtime = api["ASMCMRuntime"](
        args.checkpoint, allowed_checkpoint_sha256={checkpoint_hash}, backend=backend,
        retrieval_head=head,
    )
    reader = _reader(args.reader_config_value, api["OllamaReader"])
    compactor = api["ExtractiveCompactor"](
        max_total_bytes=args.compact_max_total_bytes,
        max_bytes_per_memory=args.compact_max_bytes_per_memory,
        max_anchors_per_memory=args.compact_max_anchors_per_memory,
        window_radius=args.compact_window_radius,
    )
    namespace = f"multiwoz-distractor-scaling-seed-{args.seed}"
    documents = workload.base_documents + workload.distractors
    frozen = {**protocol, "system": "asm", "checkpoint_sha256": checkpoint_hash,
              "artifact_sha256": artifact_hash}
    state = json.loads(state_path.read_text()) if state_path.exists() else {
        "frozen": frozen, "ingested_documents": 0, "snapshot_store_revision": 0,
        "completed_distractor_checkpoints": [], "checkpoint_resources": {},
    }
    if state.get("frozen") != frozen:
        raise ValueError("existing ASM output belongs to a different frozen protocol")
    rows = _load_jsonl(rows_path)
    completed_rows = {
        (str(item["system"]), int(item["distractor_count"]), int(item["top_k"]),
         str(item["query_id"]))
        for item in rows
    }
    with api["SQLitePayloadStore"](database) as store:
        if snapshot_path.exists():
            runtime.restore(namespace, snapshot_path.read_bytes(),
                            expected_payload_store_revision=int(state["snapshot_store_revision"]))
        elif store.revision:
            for memory in store.list_namespace(namespace):
                runtime.write(memory)
        for distractor_count in args.distractors:
            target = len(workload.base_documents) + distractor_count
            ingested = int(state["ingested_documents"])
            while ingested < target:
                end = min(target, ingested + args.chunk_size)
                started = time.perf_counter()
                for index in range(ingested, end):
                    memory = _memory(documents[index], index, namespace, api["MemoryWrite"])
                    store.put(memory)
                    runtime.write(memory)
                snapshot = runtime.snapshot(namespace, payload_store_revision=store.revision)
                _write_atomic(snapshot_path, snapshot)
                ingested = end
                state.update({"ingested_documents": ingested,
                              "snapshot_store_revision": store.revision})
                _write_json(state_path, state)
                print(json.dumps({"phase": "asm-ingest", "history_documents": ingested,
                                  "distractors": max(0, ingested-len(workload.base_documents)),
                                  "chunk_seconds": time.perf_counter()-started}), flush=True)
            for spec in workload.queries:
                expected_keys = {
                    (system, distractor_count, top_k, spec.query_id)
                    for system in ("ASM Memory Bridge", "ASM Memory Bridge (compact)")
                    for top_k in args.top_k_values
                }
                if expected_keys <= completed_rows:
                    continue
                query = api["MemoryQuery"](
                    query_id=f"{spec.query_id}:d{distractor_count}", namespace_id=namespace,
                    requester_id=namespace, question=spec.question,
                    asked_at=datetime(2027, 1, 1, tzinfo=UTC), top_k=max(args.top_k_values),
                )
                started = time.perf_counter()
                candidates = runtime.retrieve(query)
                retrieval_ms = (time.perf_counter() - started) * 1000
                for top_k in args.top_k_values:
                    selected_candidates = tuple(candidates[:top_k])
                    evidence = _evidence_package(
                        selected_candidates, store, namespace, f"{query.query_id}:k{top_k}",
                        api["Evidence"], api["EvidencePackage"]
                    )
                    retrieved_ids = [item.memory_id for item in selected_candidates]
                    full_key = ("ASM Memory Bridge", distractor_count, top_k, spec.query_id)
                    compact_key = (
                        "ASM Memory Bridge (compact)", distractor_count, top_k, spec.query_id
                    )
                    if full_key not in completed_rows:
                        measured = call_reader_measured(reader, query, evidence, api["ReaderError"])
                        value = _row(system="ASM Memory Bridge", history_events=target,
                                     distractors=distractor_count, spec=spec, top_k=top_k,
                                     retrieved_ids=retrieved_ids, evidence=evidence,
                                     answer=measured, retrieval_ms=retrieval_ms)
                        _append_jsonl(rows_path, value); rows.append(value); completed_rows.add(full_key)
                    if compact_key not in completed_rows:
                        compact_evidence = compactor.compact(query, evidence)
                        compact_answer = call_reader_measured(
                            reader, query, compact_evidence, api["ReaderError"]
                        )
                        compact_value = _row(
                            system="ASM Memory Bridge (compact)", history_events=target,
                            distractors=distractor_count, spec=spec, top_k=top_k,
                            retrieved_ids=retrieved_ids, evidence=compact_evidence,
                            answer=compact_answer, retrieval_ms=retrieval_ms,
                        )
                        _append_jsonl(rows_path, compact_value); rows.append(compact_value)
                        completed_rows.add(compact_key)
                print(json.dumps({"phase": "asm-query", "distractors": distractor_count,
                                  "completed_reader_calls": sum(
                                      r["distractor_count"] == distractor_count for r in rows
                                  ), "total_reader_calls": len(workload.queries) * 2 * len(args.top_k_values)}), flush=True)
            metrics = runtime.state_metrics(namespace)
            snap = runtime.snapshot(namespace, payload_store_revision=store.revision)
            state["checkpoint_resources"][str(distractor_count)] = {
                "history_documents": target, "payload_store_physical_bytes": physical_store_bytes(database),
                "asm_neural_state_bytes": metrics.asm_neural_state_bytes,
                "retrieval_binding_bytes": metrics.retrieval_binding_bytes,
                "runtime_active_state_bytes": metrics.runtime_active_state_bytes,
                "binding_count": metrics.binding_count, "binding_capacity": metrics.binding_capacity,
                "eviction_count": metrics.eviction_count, **snapshot_parts(snap),
            }
            done = set(state["completed_distractor_checkpoints"]); done.add(distractor_count)
            state["completed_distractor_checkpoints"] = sorted(done)
            _write_json(state_path, state)
    summary = aggregate_sweep(rows); summary.update({"protocol": frozen,
                                               "reader": args.reader_config_value,
                                               "resources": state["checkpoint_resources"]})
    _write_json(root / "summary.json", summary)


def run_rag(args: argparse.Namespace, workload: Workload, protocol: dict[str, Any], api: dict[str, Any]) -> None:
    root = args.output_root / "rag"; root.mkdir(parents=True, exist_ok=True)
    database, state_path = root / "rag.sqlite3", root / "state.json"
    rows_path = root / "reader-context.jsonl"
    frozen = {**protocol, "system": "rag", "retriever": "sqlite-fts5-bm25"}
    state = json.loads(state_path.read_text()) if state_path.exists() else {
        "frozen": frozen, "ingested_documents": 0, "completed_distractor_checkpoints": []}
    if state.get("frozen") != frozen:
        raise ValueError("existing RAG output belongs to a different frozen protocol")
    rows = _load_jsonl(rows_path)
    completed_rows = {
        (int(item["distractor_count"]), int(item["top_k"]), str(item["query_id"]))
        for item in rows
    }
    reader = _reader(args.reader_config_value, api["OllamaReader"])
    documents = workload.base_documents + workload.distractors
    namespace = f"multiwoz-distractor-scaling-seed-{args.seed}"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE IF NOT EXISTS documents (memory_id TEXT PRIMARY KEY, occurred_at TEXT, source_id TEXT, content TEXT)")
        connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(memory_id UNINDEXED, content)")
        count = int(connection.execute("SELECT count(*) FROM documents").fetchone()[0])
        if count != int(state["ingested_documents"]):
            raise ValueError("RAG state and index disagree")
        for distractor_count in args.distractors:
            target = len(workload.base_documents) + distractor_count
            started = time.perf_counter()
            with connection:
                for index in range(count, target):
                    item = documents[index]
                    occurred = (datetime(2026, 1, 1, tzinfo=UTC)+timedelta(seconds=index)).isoformat()
                    connection.execute("INSERT INTO documents VALUES (?, ?, ?, ?)",
                                       (item.memory_id, occurred, item.source_id, item.content))
                    connection.execute("INSERT INTO documents_fts(memory_id, content) VALUES (?, ?)",
                                       (item.memory_id, item.content))
            count = target; state["ingested_documents"] = count; _write_json(state_path, state)
            print(json.dumps({"phase": "rag-ingest", "history_documents": target,
                              "distractors": distractor_count,
                              "seconds": time.perf_counter()-started}), flush=True)
            for spec in workload.queries:
                expected_keys = {(distractor_count, top_k, spec.query_id) for top_k in args.top_k_values}
                if expected_keys <= completed_rows:
                    continue
                query = api["MemoryQuery"](
                    query_id=f"{spec.query_id}:rag:d{distractor_count}", namespace_id=namespace,
                    requester_id=namespace, question=spec.question,
                    asked_at=datetime(2027, 1, 1, tzinfo=UTC), top_k=max(args.top_k_values))
                started = time.perf_counter()
                selected = connection.execute(
                    "SELECT d.memory_id,d.occurred_at,d.source_id,d.content FROM documents_fts f "
                    "JOIN documents d ON d.memory_id=f.memory_id WHERE documents_fts MATCH ? "
                    "ORDER BY bm25(documents_fts),d.memory_id LIMIT ?",
                    (fts_query(spec.question), max(args.top_k_values))).fetchall()
                retrieval_ms = (time.perf_counter()-started)*1000
                all_evidence = tuple(api["Evidence"](
                    memory_id=str(item[0]), occurred_at=datetime.fromisoformat(str(item[1])),
                    source_id=str(item[2]), content=str(item[3]), score=1.0/rank)
                    for rank,item in enumerate(selected,start=1))
                for top_k in args.top_k_values:
                    key = (distractor_count, top_k, spec.query_id)
                    if key in completed_rows:
                        continue
                    evidence_items = all_evidence[:top_k]
                    evidence = api["EvidencePackage"](
                        query_id=f"{query.query_id}:k{top_k}", evidence=evidence_items,
                        omitted_candidates=0,
                        context_bytes=sum(len(item.content.encode("utf-8")) for item in evidence_items),
                        provenance_complete=True, policy_version="pmsb-multiwoz-rag-v1")
                    measured = call_reader_measured(reader, query, evidence, api["ReaderError"])
                    value = _row(system="RAG (SQLite FTS5/BM25)", history_events=target,
                                 distractors=distractor_count, spec=spec, top_k=top_k,
                                 retrieved_ids=[item.memory_id for item in evidence_items], evidence=evidence,
                                 answer=measured, retrieval_ms=retrieval_ms)
                    _append_jsonl(rows_path,value); rows.append(value); completed_rows.add(key)
            done=set(state["completed_distractor_checkpoints"]); done.add(distractor_count)
            state["completed_distractor_checkpoints"]=sorted(done); _write_json(state_path,state)
    finally:
        connection.close()
    summary=aggregate_sweep(rows); summary.update({"protocol":frozen,"reader":args.reader_config_value})
    _write_json(root/"summary.json",summary)


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distractors",type=parse_distractor_checkpoints,
                        default=parse_distractor_checkpoints("0,100,1000"))
    parser.add_argument("--queries",type=int,default=20)
    parser.add_argument("--top-k-values",type=parse_top_k_values,
                        default=parse_top_k_values("5,10,20"))
    parser.add_argument("--quality-recall-floor",type=float,default=QUALITY_RECALL_FLOOR)
    parser.add_argument("--quality-qa-floor",type=float,default=QUALITY_QA_FLOOR)
    parser.add_argument("--seed",type=int,default=1)
    parser.add_argument("--chunk-size",type=int,default=10)
    parser.add_argument("--capacity",type=int,default=1024)
    parser.add_argument("--compact-max-total-bytes",type=int,default=6144)
    parser.add_argument("--compact-max-bytes-per-memory",type=int,default=1536)
    parser.add_argument("--compact-max-anchors-per-memory",type=int,default=6)
    parser.add_argument("--compact-window-radius",type=int,default=2)
    parser.add_argument("--checkpoint",type=Path,required=True)
    parser.add_argument("--artifact",type=Path,required=True)
    parser.add_argument("--asm-source-root",type=Path,required=True)
    parser.add_argument("--bridge-source-root",type=Path,required=True)
    parser.add_argument("--multiwoz-root",type=Path,required=True)
    parser.add_argument("--phase8-results",type=Path,required=True)
    parser.add_argument("--reader-config",type=Path,required=True)
    parser.add_argument("--device",choices=("auto","cpu","cuda"),default="cuda")
    parser.add_argument("--output-root",type=Path,required=True)
    args=parser.parse_args()
    if args.queries<1 or args.chunk_size<1 or args.capacity<1:
        parser.error("queries, chunk-size and capacity must be positive")
    if not 0 <= args.quality_recall_floor <= 1 or not 0 <= args.quality_qa_floor <= 1:
        parser.error("quality floors must be between zero and one")
    compact_limits = (
        args.compact_max_total_bytes,
        args.compact_max_bytes_per_memory,
        args.compact_max_anchors_per_memory,
    )
    if any(value < 1 for value in compact_limits) or args.compact_window_radius < 0:
        parser.error("compactor byte/anchor limits must be positive and radius non-negative")
    for source in (args.bridge_source_root/"src",args.bridge_source_root,args.asm_source_root/"src"):
        value=str(source.resolve())
        if value not in sys.path: sys.path.insert(0,value)
    from asm_memory_bridge import (
        ASMCMRuntime, Evidence, EvidencePackage, ExtractiveCompactor, MemoryQuery, MemoryWrite
    )
    from asm_memory_bridge.errors import ReaderError
    from asm_memory_bridge.readers.ollama import OllamaReader
    from asm_memory_bridge.retrieval.torch_head import TorchIDRetrievalHead
    from asm_memory_bridge.runtime.torch_backend import TorchASMCMBackend
    from asm_memory_bridge.stores import SQLitePayloadStore
    api=locals()
    args.reader_config_value=_load_reader_config(args.reader_config)
    workload=load_workload(args.multiwoz_root,args.phase8_results,query_count=args.queries,
                           distractor_count=max(args.distractors))
    protocol=_protocol(args,workload,args.reader_config_value)
    args.output_root.mkdir(parents=True,exist_ok=True)
    _write_json(args.output_root/"protocol.json",protocol)
    run_asm(args,workload,protocol,api)
    run_rag(args,workload,protocol,api)
    asm_rows=_load_jsonl(args.output_root/"asm"/"reader-context.jsonl")
    rag_rows=_load_jsonl(args.output_root/"rag"/"reader-context.jsonl")
    expected = {
        (len(workload.base_documents) + distractors, top_k, spec.query_id)
        for distractors in args.distractors for top_k in args.top_k_values
        for spec in workload.queries
    }
    for system in ("ASM Memory Bridge", "ASM Memory Bridge (compact)"):
        keys = {
            (int(row["history_events"]), int(row["top_k"]), str(row["query_id"]))
            for row in asm_rows if row["system"] == system
        }
        if keys != expected:
            raise ValueError(f"{system} does not contain the frozen checkpoint/query pairs")
    rag_keys = {
        (int(row["history_events"]), int(row["top_k"]), str(row["query_id"]))
        for row in rag_rows
    }
    if rag_keys != expected:
        raise ValueError("RAG does not contain the frozen checkpoint/query pairs")
    readers = {str(row["reader_model"]) for row in asm_rows + rag_rows}
    if len(readers) != 1:
        raise ValueError("all three systems must use the same reader")
    result=aggregate_sweep(asm_rows+rag_rows)
    result.update({"comparison_status":"paired-measured-top-k-sweep","protocol":protocol})
    _write_json(args.output_root/"top-k-sweep-summary.json",result)
    render_top_k_sweep(result,args.output_root/"top-k-sweep.png",
                       args.output_root/"top-k-sweep.svg")
    frontier=quality_frontier(result,recall_floor=args.quality_recall_floor,
                              qa_floor=args.quality_qa_floor)
    frontier["protocol"]=protocol
    _write_json(args.output_root/"quality-matched-summary.json",frontier)
    render_quality_frontier(frontier,args.output_root/"quality-matched.png",
                            args.output_root/"quality-matched.svg")
    print(json.dumps({"status":"complete",
                      "graph":str(args.output_root/"quality-matched.png"),
                      "quality_matched_points":len(frontier["points"])},indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
