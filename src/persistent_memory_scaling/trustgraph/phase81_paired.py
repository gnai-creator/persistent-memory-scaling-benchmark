"""Paired MultiWOZ Phase 8.1 questions over TrustGraph graph embeddings."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from .preflight import write_json
from .corpora import load_instances


def entity_uri(memory_id: str) -> str:
    digest = hashlib.sha256(memory_id.encode()).hexdigest()
    return f"urn:pmsb:multiwoz:memory:{digest}"


def _term_uri(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("i") or value.get("v") or value.get("value") or "")
    for attribute in ("i", "v", "value", "uri"):
        candidate = getattr(value, attribute, None)
        if candidate:
            return str(candidate)
    return str(value)


def decode_matches(result: Any, uri_to_memory: dict[str, str]) -> list[tuple[str, float]]:
    rows = result.get("entities", []) if isinstance(result, dict) else getattr(result, "entities", [])
    decoded = []
    for row in rows:
        entity = row.get("entity") if isinstance(row, dict) else getattr(row, "entity", None)
        score = row.get("score", 0.0) if isinstance(row, dict) else getattr(row, "score", 0.0)
        uri = _term_uri(entity)
        if uri in uri_to_memory:
            decoded.append((uri_to_memory[uri], float(score)))
    return decoded


def graph_embeddings_query(flow: Any, text: str, collection: str, limit: int) -> Any:
    """Call the public services despite the SDK's double-unwrapping bug."""
    vectors = flow.embeddings(texts=[text])
    return flow.request("service/graph-embeddings", {
        "vector": vectors[0], "collection": collection, "limit": limit,
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8888/")
    parser.add_argument("--token")
    parser.add_argument("--token-env", default="IAM_BOOTSTRAP_TOKEN")
    parser.add_argument("--flow", default="default")
    parser.add_argument("--collection", required=True)
    parser.add_argument("--asm-root", type=Path, required=True)
    parser.add_argument("--corpus", choices=("multiwoz979", "free128", "longmemeval500"), default="multiwoz979")
    parser.add_argument("--multiwoz-root", type=Path)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--retrieval-root", type=Path)
    parser.add_argument("--phase8-results", type=Path, dest="frozen_results", required=True)
    parser.add_argument("--reader-protocol-results", type=Path)
    parser.add_argument("--official-evaluator-root", type=Path)
    parser.add_argument("--official-python", type=Path)
    parser.add_argument("--oracle-dataset", type=Path)
    parser.add_argument("--official-judge-model", default="gpt-4o")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-examples", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--collection-timeout-seconds", type=int, default=30)
    parser.add_argument("--collection-attempts", type=int, default=4)
    parser.add_argument("--collection-retry-delay-seconds", type=float, default=2.0)
    parser.add_argument("--collection-pacing-seconds", type=float, default=0.05)
    args = parser.parse_args()
    if args.collection_attempts < 1:
        parser.error("--collection-attempts must be at least 1")
    if args.collection_timeout_seconds < 1:
        parser.error("--collection-timeout-seconds must be at least 1")
    if args.collection_retry_delay_seconds < 0 or args.collection_pacing_seconds < 0:
        parser.error("collection retry and pacing delays cannot be negative")

    token = args.token or os.environ.get(args.token_env, "")
    if not token:
        parser.error(f"TrustGraph token required via --token or {args.token_env}")

    sys.path[:0] = [str(args.asm_root), str(args.asm_root / "src")]
    from asm_memory_bridge import RetrievalCandidate
    from benchmarks.multiwoz.phase8 import evaluate_one, metric_summary
    from benchmarks.multiwoz.phase81 import reader_from_protocol
    from persistent_memory_scaling.trustgraph.client import TrustGraphClient

    instances, reader_protocol = load_instances(
        args.corpus, asm_root=args.asm_root, frozen_results=args.frozen_results,
        multiwoz_root=args.multiwoz_root, dataset=args.dataset,
        retrieval_root=args.retrieval_root,
    )
    if args.max_examples:
        instances = instances[:args.max_examples]
    if args.reader_protocol_results:
        reader_protocol = json.loads(
            args.reader_protocol_results.read_text(encoding="utf-8")
        )["protocol"]
    if not reader_protocol:
        parser.error("reader protocol is absent; pass --reader-protocol-results")
    memories = {memory.memory_id: memory for item in instances for memory in item.memories}
    memory_to_uri = {memory_id: entity_uri(memory_id) for memory_id in memories}
    uri_to_memory = {uri: memory_id for memory_id, uri in memory_to_uri.items()}
    signatures = sorted({tuple(memory.memory_id for memory in item.memories) for item in instances})
    collection_for_signature = {
        signature: f"{args.collection}-b{index:02d}"
        for index, signature in enumerate(signatures, 1)
    }

    client = TrustGraphClient(args.url, token, flow_id=args.flow, collection=args.collection)
    setup_started = perf_counter()
    collections = client.api.collection()
    known_collections = {item.collection for item in collections.list_collections()}
    created_collections = 0
    for index, collection_name in enumerate(collection_for_signature.values(), 1):
        if collection_name in known_collections:
            continue
        for attempt in range(1, args.collection_attempts + 1):
            try:
                # Recreate the short-timeout administrative client on every attempt.
                # A timed-out request/response client may still have an outstanding
                # backend operation and must not be silently reused.
                admin = TrustGraphClient(
                    args.url, token, flow_id=args.flow, collection=args.collection,
                    timeout=args.collection_timeout_seconds,
                )
                admin.api.collection().update_collection(
                    collection=collection_name,
                    name=f"PMSB {args.corpus} bundle {index:03d}",
                    description=f"One frozen {args.corpus} candidate corpus",
                    tags=["pmsb", args.corpus, "paired", "bundle"],
                )
                known_collections.add(collection_name)
                created_collections += 1
                print(
                    f"[collection {index}/{len(collection_for_signature)}] "
                    f"registered attempt={attempt}",
                    flush=True,
                )
                break
            except Exception as exc:
                print(
                    f"[collection {index}/{len(collection_for_signature)}] "
                    f"attempt {attempt} failed: {type(exc).__name__}: {exc}",
                    file=sys.stderr, flush=True,
                )
                if attempt == args.collection_attempts:
                    raise
                time.sleep(args.collection_retry_delay_seconds)
        if args.collection_pacing_seconds:
            time.sleep(args.collection_pacing_seconds)
    if created_collections:
        time.sleep(2)
    setup_seconds = perf_counter() - setup_started
    ingestion_started = perf_counter()
    for index, signature in enumerate(signatures, 1):
        contexts = (
            {"entity": {"t": "i", "i": memory_to_uri[memory_id]},
             "context": memories[memory_id].content}
            for memory_id in signature
        )
        client.api.bulk().import_entity_contexts(
            flow=args.flow, contexts=contexts,
            metadata={"id": f"pmsb-phase81-bundle-{index:02d}", "metadata": [],
                      "collection": collection_for_signature[signature]},
        )
    ingestion_submission_seconds = perf_counter() - ingestion_started

    indexing_started = perf_counter()
    deadline = time.monotonic() + 600
    readiness_raw: list[Any] = []
    while time.monotonic() < deadline:
        readiness_raw = [
            graph_embeddings_query(
                client.api.flow().id(args.flow), memories[signature[-1]].content,
                collection_for_signature[signature], limit=5)
            for signature in signatures
        ]
        decoded_sentinels = [decode_matches(raw, uri_to_memory) for raw in readiness_raw]
        if all(any(memory_id == signature[-1] for memory_id, _ in matches)
               for signature, matches in zip(signatures, decoded_sentinels, strict=True)):
            break
        time.sleep(2)
    else:
        raise TimeoutError(f"TrustGraph embeddings not queryable after import: {readiness_raw!r}")
    indexing_readiness_seconds = perf_counter() - indexing_started

    rows = []
    if args.resume and args.output.exists():
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        rows = list(previous.get("rows", []))
    completed = {row["question_id"] for row in rows}
    reader_args = type("ReaderArgs", (), {
        "timeout_seconds": 180.0, "reader_attempts": 5, "retry_delay_seconds": 1.0,
        "reader_api_key_env": "",
    })()
    reader = reader_from_protocol(reader_args, reader_protocol)
    top_k = int(reader_protocol["top_k"])
    for index, instance in enumerate(instances, 1):
        if instance.question_id in completed:
            continue
        retrieval_started = perf_counter()
        signature = tuple(memory.memory_id for memory in instance.memories)
        raw = graph_embeddings_query(
            client.api.flow().id(args.flow), instance.question,
            collection_for_signature[signature], limit=top_k)
        matches = decode_matches(raw, uri_to_memory)[:top_k]
        retrieval_ms = (perf_counter() - retrieval_started) * 1000
        candidates = tuple(RetrievalCandidate(
            memory_id=memory_id, score=max(0.0, min(1.0, score)), rank=rank,
            retrieval_reason="TrustGraph graph-embeddings query",
        ) for rank, (memory_id, score) in enumerate(matches, 1))
        row = evaluate_one(
            instance, "trustgraph_graph_embeddings", candidates=candidates, reader=reader,
            max_context_bytes=int(reader_protocol["max_context_bytes"]),
            retrieval_latency_ms=retrieval_ms,
            input_price_per_million=float(reader_protocol.get("input_price_per_million", 0.0)),
            output_price_per_million=float(reader_protocol.get("output_price_per_million", 0.0)),
        )
        rows.append(row)
        partial = {
            "schema_version": "tg-paired-corpus-v1", "corpus": args.corpus, "collection": args.collection,
            "system": "trustgraph_graph_embeddings", "examples_requested": len(instances),
            "unique_memories": len(memories), "bundle_count": len(signatures),
            "candidate_memories_per_question": 16, "setup_seconds": setup_seconds,
            "ingestion_submission_seconds": ingestion_submission_seconds,
            "indexing_readiness_seconds": indexing_readiness_seconds,
            "rows": rows,
        }
        write_json(args.output, partial)
        print(f"[{index}/{len(instances)}] recall={row['retrieval_recall']:.0f} "
              f"score={row['diagnostic_answer_score']:.3f} tokens={row['reader_input_tokens']}",
              flush=True)

    summary = metric_summary(rows)
    official: dict[str, Any] = {"status": "not_applicable"}
    if args.corpus == "longmemeval500":
        required = (args.official_evaluator_root, args.official_python, args.oracle_dataset)
        if any(value is None for value in required):
            parser.error("LongMemEval requires official evaluator root, Python, and oracle dataset")
        from .longmemeval_official import evaluate as evaluate_official
        official = evaluate_official(
            rows, system="trustgraph_graph_embeddings_gpt4o", output=args.output,
            evaluator_root=args.official_evaluator_root,
            evaluator_python=args.official_python, oracle_dataset=args.oracle_dataset,
            judge_model=args.official_judge_model,
        )
    result = {
        "schema_version": "tg-paired-corpus-v1", "corpus": args.corpus, "collection": args.collection,
        "system": "trustgraph_graph_embeddings", "examples_requested": len(instances),
        "unique_memories": len(memories), "bundle_count": len(signatures),
        "candidate_memories_per_question": 16, "setup_seconds": setup_seconds,
        "ingestion_submission_seconds": ingestion_submission_seconds,
        "indexing_readiness_seconds": indexing_readiness_seconds,
        "retrieval_latency_ms_mean_external": mean(row["retrieval_latency_ms"] for row in rows),
        "summary": summary, "official_evaluation": official,
        "complete": len(rows) == len(instances), "rows": rows,
        "limitations": [
            "Graph-embeddings retrieval is a TrustGraph retrieval ablation, not full GraphRAG synthesis.",
            "MultiWOZ memories were imported as entity contexts to preserve one retrievable ID per dialogue.",
            "Each question searches only its frozen 16-memory Phase 8.1 bundle, matching the ASM, Vector RAG, and BM25 candidate corpus.",
            "Collection setup, ingestion submission, and indexing readiness are excluded from query latency.",
        ],
    }
    write_json(args.output, result)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
