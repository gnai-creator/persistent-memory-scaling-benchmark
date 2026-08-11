"""Paired MultiWOZ Phase 8.1 questions over TrustGraph graph embeddings."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from .preflight import write_json


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
    parser.add_argument("--token", required=True)
    parser.add_argument("--flow", default="default")
    parser.add_argument("--collection", required=True)
    parser.add_argument("--asm-root", type=Path, required=True)
    parser.add_argument("--multiwoz-root", type=Path, required=True)
    parser.add_argument("--phase8-results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-examples", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    sys.path[:0] = [str(args.asm_root), str(args.asm_root / "src")]
    from asm_memory_bridge import RetrievalCandidate
    from benchmarks.multiwoz.adapter import load_multiwoz
    from benchmarks.multiwoz.phase8 import evaluate_one, metric_summary
    from benchmarks.multiwoz.phase81 import reader_from_protocol
    from persistent_memory_scaling.trustgraph.client import TrustGraphClient

    phase8 = json.loads(args.phase8_results.read_text(encoding="utf-8"))
    frozen_ids = [str(value) for value in phase8["protocol"]["evaluation_question_ids"]]
    if args.max_examples:
        frozen_ids = frozen_ids[:args.max_examples]
    loaded = load_multiwoz(args.multiwoz_root, "test", bundle_size=16,
                           maximum=int(phase8["protocol"]["source_evaluation_examples"]))
    by_id = {item.question_id: item for item in loaded}
    instances = [by_id[value] for value in frozen_ids]
    memories = {memory.memory_id: memory for item in instances for memory in item.memories}
    memory_to_uri = {memory_id: entity_uri(memory_id) for memory_id in memories}
    uri_to_memory = {uri: memory_id for memory_id, uri in memory_to_uri.items()}
    signatures = sorted({tuple(memory.memory_id for memory in item.memories) for item in instances})
    collection_for_signature = {
        signature: f"{args.collection}-b{index:02d}"
        for index, signature in enumerate(signatures, 1)
    }

    client = TrustGraphClient(args.url, args.token, flow_id=args.flow, collection=args.collection)
    setup_started = perf_counter()
    collections = client.api.collection()
    known_collections = {item.collection for item in collections.list_collections()}
    for index, collection_name in enumerate(collection_for_signature.values(), 1):
        if collection_name in known_collections:
            continue
        collections.update_collection(
            collection=collection_name,
            name=f"PMSB Phase 8.1 bundle {index:02d}",
            description="One frozen 16-memory MultiWOZ Phase 8.1 candidate corpus",
            tags=["pmsb", "phase81", "paired", "bundle"],
        )
    if any(name not in known_collections for name in collection_for_signature.values()):
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
    reader = reader_from_protocol(reader_args, phase8["protocol"])
    top_k = int(phase8["protocol"]["top_k"])
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
            max_context_bytes=int(phase8["protocol"]["max_context_bytes"]),
            retrieval_latency_ms=retrieval_ms,
            input_price_per_million=float(phase8["protocol"]["input_price_per_million"]),
            output_price_per_million=float(phase8["protocol"]["output_price_per_million"]),
        )
        rows.append(row)
        partial = {
            "schema_version": "tg-phase81-paired-v1", "collection": args.collection,
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
    result = {
        "schema_version": "tg-phase81-paired-v1", "collection": args.collection,
        "system": "trustgraph_graph_embeddings", "examples_requested": len(instances),
        "unique_memories": len(memories), "bundle_count": len(signatures),
        "candidate_memories_per_question": 16, "setup_seconds": setup_seconds,
        "ingestion_submission_seconds": ingestion_submission_seconds,
        "indexing_readiness_seconds": indexing_readiness_seconds,
        "retrieval_latency_ms_mean_external": mean(row["retrieval_latency_ms"] for row in rows),
        "summary": summary, "complete": len(rows) == len(instances), "rows": rows,
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
