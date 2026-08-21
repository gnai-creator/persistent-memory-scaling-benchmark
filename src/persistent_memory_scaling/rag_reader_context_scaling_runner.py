"""Run the paired SQLite FTS5/BM25 RAG baseline with the frozen local reader."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .asm_reader_context_scaling_runner import (
    _append_jsonl,
    _load_jsonl,
    _load_reader_config,
    _sha256,
    _write_json,
    answer_quality,
    call_reader_measured,
    parse_checkpoints,
)
from .asm_tg2_runner import canonical_event_content
from .reader_context_scaling import aggregate, render
from .trustgraph.tg2 import TG2_SEED, generate_event, generate_queries


def fts_query(question: str) -> str:
    terms = re.findall(r"[A-Za-zÀ-ÿ0-9]+", question.casefold())
    useful = list(dict.fromkeys(term for term in terms if len(term) >= 2 or term.isdigit()))
    if not useful:
        raise ValueError("query has no FTS terms")
    return " OR ".join(f'"{term}"' for term in useful)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoints", type=parse_checkpoints, default=parse_checkpoints("10000,100000,1000000"))
    parser.add_argument("--queries", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=TG2_SEED)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--bridge-source-root", type=Path, required=True)
    parser.add_argument("--reader-config", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if args.queries < 1 or args.top_k < 1:
        parser.error("queries and top-k must be positive")

    bridge_source = str((args.bridge_source_root / "src").resolve())
    if bridge_source not in sys.path:
        sys.path.insert(0, bridge_source)
    from asm_memory_bridge import Evidence, EvidencePackage, MemoryQuery
    from asm_memory_bridge.errors import ReaderError
    from asm_memory_bridge.readers.ollama import OllamaReader

    config = _load_reader_config(args.reader_config)
    generation = config["generation"]
    reader = OllamaReader(
        model=config["model"], base_url=config["base_url"],
        temperature=float(generation["temperature"]), seed=int(generation["seed"]),
        num_ctx=int(generation["num_ctx"]), max_new_tokens=int(generation["max_new_tokens"]),
        think=bool(generation["think"]), attempts=int(generation.get("attempts", 2)),
        retry_delay_seconds=float(generation.get("retry_delay_seconds", 1)),
        timeout_seconds=float(generation.get("timeout_seconds", 120)),
    )

    args.output_root.mkdir(parents=True, exist_ok=True)
    database = args.output_root / "rag.sqlite3"
    rows_path = args.output_root / "reader-context.jsonl"
    summary_path = args.output_root / "summary.json"
    manifest_path = args.output_root / "manifest.json"
    png_path = args.output_root / "reader-context-scaling.png"
    svg_path = args.output_root / "reader-context-scaling.svg"
    state_path = args.output_root / "state.json"
    frozen = {"checkpoints": args.checkpoints, "queries": args.queries, "seed": args.seed,
              "top_k": args.top_k, "reader_config_sha256": _sha256(args.reader_config),
              "retriever": "sqlite-fts5-bm25"}
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {
        "schema_version": "rag-reader-scaling-state-v1", "ingested_events": 0,
        "completed_checkpoints": [], "frozen": frozen,
    }
    if state.get("frozen") != frozen:
        raise ValueError("existing RAG output belongs to a different frozen protocol")

    rows = _load_jsonl(rows_path)
    completed_rows = {(int(row["history_events"]), str(row["query_id"])) for row in rows}
    query_specs = generate_queries(args.checkpoints[0], args.seed, args.queries)
    namespace = f"tg2-reader-scaling-{args.seed}"
    base_time = datetime(2026, 1, 1, tzinfo=UTC)
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE IF NOT EXISTS documents (memory_id TEXT PRIMARY KEY, occurred_at TEXT NOT NULL, source_id TEXT NOT NULL, content TEXT NOT NULL)")
        connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(memory_id UNINDEXED, content)")
        actual_count = int(connection.execute("SELECT count(*) FROM documents").fetchone()[0])
        if actual_count != int(state["ingested_events"]):
            raise ValueError("RAG state and document index disagree")

        for checkpoint in args.checkpoints:
            completed = set(int(item) for item in state["completed_checkpoints"])
            row_count = sum(1 for row in rows if int(row["history_events"]) == checkpoint)
            if checkpoint in completed:
                if row_count != args.queries:
                    raise ValueError(f"RAG checkpoint {checkpoint} is incomplete")
                continue
            ingested = int(state["ingested_events"])
            if ingested > checkpoint:
                raise ValueError("cannot evaluate an incomplete RAG checkpoint after later ingestion")
            started = time.perf_counter()
            with connection:
                for index in range(ingested, checkpoint):
                    event = generate_event(index, args.seed)
                    content = canonical_event_content(event)
                    occurred_at = (base_time + timedelta(microseconds=index)).isoformat()
                    connection.execute("INSERT INTO documents VALUES (?, ?, ?, ?)",
                                       (event["event_id"], occurred_at, event["relevant_evidence_ids"][0], content))
                    connection.execute("INSERT INTO documents_fts(memory_id, content) VALUES (?, ?)",
                                       (event["event_id"], content))
            state["ingested_events"] = checkpoint
            _write_json(state_path, state)
            print(json.dumps({"phase": "rag-ingest", "events": checkpoint,
                              "seconds": time.perf_counter() - started}), flush=True)

            for spec in query_specs:
                key = (checkpoint, spec["query_id"])
                if key in completed_rows:
                    continue
                asked_at = base_time + timedelta(days=1)
                query = MemoryQuery(
                    query_id=f"{spec['query_id']}-rag-at-{checkpoint}", namespace_id=namespace,
                    requester_id=namespace, question=spec["question"], asked_at=asked_at,
                    top_k=args.top_k,
                )
                retrieval_started = time.perf_counter()
                selected = connection.execute(
                    "SELECT d.memory_id, d.occurred_at, d.source_id, d.content "
                    "FROM documents_fts f JOIN documents d ON d.memory_id=f.memory_id "
                    "WHERE documents_fts MATCH ? ORDER BY bm25(documents_fts), d.memory_id LIMIT ?",
                    (fts_query(spec["question"]), args.top_k),
                ).fetchall()
                retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
                evidence = tuple(Evidence(
                    memory_id=str(item[0]), occurred_at=datetime.fromisoformat(str(item[1])),
                    source_id=str(item[2]), content=str(item[3]), score=1.0 / rank,
                ) for rank, item in enumerate(selected, start=1))
                package = EvidencePackage(
                    query_id=query.query_id, evidence=evidence, omitted_candidates=0,
                    context_bytes=sum(len(item.content.encode("utf-8")) for item in evidence),
                    provenance_complete=True, policy_version="pmsb-tg2-rag-v1",
                )
                answer = call_reader_measured(reader, query, package, ReaderError)
                expected_ids = {item.replace("evidence", "event") for item in spec["relevant_evidence_ids"]}
                retrieved_ids = [item.memory_id for item in evidence]
                row = {
                    "system": "RAG (SQLite FTS5/BM25)", "history_events": checkpoint,
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
            completed.add(checkpoint)
            state["completed_checkpoints"] = sorted(completed)
            _write_json(state_path, state)
    finally:
        connection.close()

    summary = aggregate(rows)
    summary["protocol"] = frozen
    summary["reader"] = config
    summary["retriever_note"] = "Explicit full-history lexical RAG baseline using SQLite FTS5 BM25."
    _write_json(summary_path, summary)
    render(summary, png_path, svg_path)
    _write_json(manifest_path, {"schema_version": "rag-reader-context-scaling-manifest-v1",
                                "status": "complete", "artifacts": {
                                    path.name: _sha256(path) for path in (rows_path, summary_path, png_path, svg_path)
                                }})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
