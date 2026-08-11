"""End-to-end TrustGraph Full GraphRAG on frozen MultiWOZ Phase 8.1."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Any

from .phase81_paired import entity_uri
from .corpora import load_instances
from .preflight import write_json

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
PMSB = "urn:pmsb:multiwoz:"


def retry_call(
    operation: Callable[[], Any],
    *,
    label: str,
    max_attempts: int,
    initial_delay_seconds: float,
    max_delay_seconds: float,
) -> tuple[Any, int]:
    """Retry transient TrustGraph failures; max_attempts=0 means keep trying."""
    attempt = 0
    while True:
        attempt += 1
        try:
            return operation(), attempt
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            if max_attempts > 0 and attempt >= max_attempts:
                raise
            delay = min(
                max_delay_seconds,
                initial_delay_seconds * (2 ** min(attempt - 1, 8)),
            )
            print(
                f"[{label}] attempt {attempt} failed: {type(exc).__name__}: {exc}; "
                f"retrying in {delay:.0f}s",
                flush=True,
            )
            time.sleep(delay)


def source_uri(source_id: str) -> str:
    return f"urn:pmsb:source:{source_id.replace(':', '/')}"


def source_memory_ids(sources: list[Any], uri_to_memory: dict[str, str]) -> list[str]:
    found: list[str] = []
    for source in sources:
        uri = str(source.get("uri", "") if isinstance(source, dict) else getattr(source, "uri", ""))
        memory_id = uri_to_memory.get(uri)
        if memory_id and memory_id not in found:
            found.append(memory_id)
    return found


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    source_mappable = [row for row in rows if row["sources_mappable"]]
    grounding_complete = [row for row in rows if row.get("grounding_recall_at_5") is not None]
    result = {
        "examples": len(rows),
        "diagnostic_answer_score": statistics.fmean(row["diagnostic_answer_score"] for row in rows),
        "token_f1": statistics.fmean(row["token_f1"] for row in rows),
        "answer_containment": statistics.fmean(float(row["answer_containment"]) for row in rows),
        "exact_match": statistics.fmean(float(row["exact_match"]) for row in rows),
        "full_graphrag_latency_ms_mean": statistics.fmean(row["full_graphrag_latency_ms"] for row in rows),
        "full_graphrag_input_tokens_total": sum(row["input_tokens"] for row in rows),
        "full_graphrag_output_tokens_total": sum(row["output_tokens"] for row in rows),
        "token_usage_complete": all(row["input_tokens"] > 0 for row in rows),
        "source_mapping_coverage": len(source_mappable) / len(rows),
        "source_recall_at_5": (
            statistics.fmean(float(row["source_recall_at_5"]) for row in source_mappable)
            if source_mappable else None
        ),
        "grounding_mapping_coverage": len(grounding_complete) / len(rows),
        "grounding_recall_at_5": (
            statistics.fmean(float(row["grounding_recall_at_5"]) for row in grounding_complete)
            if grounding_complete else None
        ),
        "explain_replay_latency_ms_mean": (
            statistics.fmean(row["explain_replay_latency_ms"] for row in grounding_complete)
            if grounding_complete else None
        ),
    }
    grounding_15 = [row for row in rows if row.get("grounding_recall_at_15") is not None]
    source_15 = [row for row in rows if row.get("source_recall_at_15") is not None]
    if grounding_15:
        result["grounding_recall_at_15"] = statistics.fmean(
            float(row["grounding_recall_at_15"]) for row in grounding_15
        )
    if source_15:
        result["source_recall_at_15"] = statistics.fmean(
            float(row["source_recall_at_15"]) for row in source_15
        )
    return result


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
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-examples", type=int, default=0)
    parser.add_argument(
        "--question-id",
        help="Run exactly one question while retaining the canonical collection mapping",
    )
    parser.add_argument(
        "--reuse-existing-collections",
        action="store_true",
        help="Skip ingestion and use the already indexed canonical collections",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--max-attempts", type=int, default=0,
        help="Attempts per GraphRAG/explainability call; 0 retries until success",
    )
    parser.add_argument("--retry-delay-seconds", type=float, default=330.0)
    parser.add_argument("--max-retry-delay-seconds", type=float, default=600.0)
    parser.add_argument("--request-timeout-seconds", type=int, default=600)
    parser.add_argument("--official-evaluator-root", type=Path)
    parser.add_argument("--official-python", type=Path)
    parser.add_argument("--oracle-dataset", type=Path)
    parser.add_argument("--official-judge-model", default="gpt-4o")
    parser.add_argument("--ensure-flow-model")
    parser.add_argument("--ensure-flow-embeddings-model", default="nomic-embed-text")
    args = parser.parse_args()
    if args.max_attempts < 0:
        parser.error("--max-attempts cannot be negative")
    if args.retry_delay_seconds < 0 or args.max_retry_delay_seconds < 0:
        parser.error("retry delays cannot be negative")
    token = args.token or os.environ.get(args.token_env, "")
    if not token:
        parser.error(f"TrustGraph token required via --token or {args.token_env}")
    previous_payload: dict[str, Any] = {}
    if args.resume and args.output.exists():
        previous_payload = json.loads(args.output.read_text(encoding="utf-8"))

    sys.path[:0] = [str(args.asm_root), str(args.asm_root / "src")]
    from benchmarks.longmemeval.scoring import token_f1, token_sequence_containment
    from persistent_memory_scaling.trustgraph.client import TrustGraphClient
    from trustgraph.api import Triple

    all_instances, _ = load_instances(
        args.corpus, asm_root=args.asm_root, frozen_results=args.frozen_results,
        multiwoz_root=args.multiwoz_root, dataset=args.dataset,
        retrieval_root=args.retrieval_root,
    )
    instances = all_instances
    if args.question_id:
        instances = [item for item in all_instances if item.question_id == args.question_id]
        if not instances:
            parser.error(f"unknown --question-id: {args.question_id}")
    if args.max_examples:
        instances = instances[: args.max_examples]
    # Collection numbering must remain stable even for a one-question diagnostic.
    # It is derived from the complete frozen corpus, not from the selected subset.
    signatures = sorted({
        tuple(memory.memory_id for memory in item.memories) for item in all_instances
    })
    memories = {
        memory.memory_id: memory for item in all_instances for memory in item.memories
    }
    collections = {
        signature: f"{args.collection}-full-b{index:02d}"
        for index, signature in enumerate(signatures, 1)
    }
    uri_to_memory = {
        uri: memory_id
        for memory_id, memory in memories.items()
        for uri in (entity_uri(memory_id), source_uri(memory.source_id))
    }

    client = TrustGraphClient(
        args.url, token, flow_id=args.flow, collection=args.collection,
        timeout=args.request_timeout_seconds,
    )
    if args.ensure_flow_model:
        client.start_flow(args.ensure_flow_model, args.ensure_flow_embeddings_model)
    collection_api = client.api.collection()
    known = {item.collection for item in collection_api.list_collections()}
    for index, collection in enumerate(collections.values(), 1):
        if collection not in known:
            collection_api.update_collection(
                collection=collection, name=f"PMSB Full GraphRAG bundle {index:02d}",
                description="Frozen 16-memory MultiWOZ graph for the Full GraphRAG ablation",
                tags=["pmsb", "phase81", "full-graphrag", "paired"],
            )
    time.sleep(2)

    ingestion_submission_seconds = float(
        previous_payload.get("ingestion_submission_seconds", 0.0)
    )
    if not previous_payload.get("rows") and not args.reuse_existing_collections:
        ingestion_started = perf_counter()
        for signature in signatures:
            collection = collections[signature]
            bundle_uri = f"{PMSB}bundle:{signature[0].rsplit(':', 1)[-1]}"
            for memory_id in signature:
                memory = memories[memory_id]
                memory_uri = entity_uri(memory_id)
                triples = [
                    Triple(s=memory_uri, p=RDF_TYPE, o=f"{PMSB}Memory"),
                    Triple(s=memory_uri, p=RDFS_LABEL, o=memory_id,
                           o_datatype="http://www.w3.org/2001/XMLSchema#string"),
                    Triple(s=memory_uri, p=f"{PMSB}dialogue", o=memory.content,
                           o_datatype="http://www.w3.org/2001/XMLSchema#string"),
                    Triple(s=memory_uri, p=f"{PMSB}source", o=source_uri(memory.source_id)),
                    Triple(s=bundle_uri, p=f"{PMSB}contains", o=memory_uri),
                ]
                metadata = {
                    "id": memory.source_id, "metadata": [], "collection": collection
                }
                client.api.bulk().import_triples(
                    flow=args.flow, triples=iter(triples), metadata=metadata
                )
                client.api.bulk().import_entity_contexts(
                    flow=args.flow,
                    contexts=iter(({
                        "entity": {"t": "i", "i": memory_uri},
                        "context": memory.content,
                    },)),
                    metadata=metadata,
                )
        ingestion_submission_seconds = perf_counter() - ingestion_started

    readiness_started = perf_counter()
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        ready = True
        for signature in signatures:
            probe = TrustGraphClient(
                args.url, token, flow_id=args.flow, collection=collections[signature],
                timeout=args.request_timeout_seconds,
            )
            if not probe.query_subject(entity_uri(signature[-1]), limit=10):
                ready = False
                break
        if ready:
            break
        time.sleep(2)
    else:
        raise TimeoutError("Full GraphRAG graph triples were not queryable after import")
    indexing_readiness_seconds = perf_counter() - readiness_started

    rows: list[dict[str, Any]] = list(previous_payload.get("rows", []))
    if rows:
        write_json(args.output, {
            **previous_payload,
            "complete": False,
            "examples_requested": len(instances),
            "rows": rows,
        })
    completed = {row["question_id"] for row in rows}
    retrieval_k = 15 if args.corpus == "longmemeval500" else 5
    flow = client.api.flow().id(args.flow)
    socket_flow = client.api.socket().flow(args.flow)

    def explain_grounding(instance: Any, collection: str) -> tuple[list[str], float, int]:
        from trustgraph.api.types import ProvenanceEvent

        started = perf_counter()
        def operation() -> list[str]:
            ranked: list[str] = []
            for item in socket_flow.graph_rag_explain(
                query=instance.question, collection=collection,
                entity_limit=20, triple_limit=20, max_subgraph_size=100,
                max_path_length=2, edge_score_limit=20, edge_limit=10,
                max_reranker_input=100,
            ):
                if not isinstance(item, ProvenanceEvent) or item.event_type != "exploration":
                    continue
                for uri in getattr(item.entity, "entities", ()):
                    memory_id = uri_to_memory.get(str(uri))
                    if memory_id and memory_id not in ranked:
                        ranked.append(memory_id)
            return ranked

        ranked, attempts = retry_call(
            operation, label=f"explain:{instance.question_id}",
            max_attempts=args.max_attempts,
            initial_delay_seconds=args.retry_delay_seconds,
            max_delay_seconds=args.max_retry_delay_seconds,
        )
        return ranked, (perf_counter() - started) * 1000, attempts

    # A resume may enrich an already completed end-to-end run with the official
    # explainability grounding ranking without repeating or replacing its answer.
    instance_by_id = {instance.question_id: instance for instance in instances}
    for row in rows:
        if row.get("grounding_recall_at_5") is not None:
            continue
        instance = instance_by_id[row["question_id"]]
        signature = tuple(memory.memory_id for memory in instance.memories)
        ranked, explain_ms, explain_attempts = explain_grounding(
            instance, collections[signature]
        )
        expected = set(instance.answer_memory_ids)
        row["graphrag_grounding_memory_ids"] = ranked
        row["grounding_recall_at_5"] = bool(expected.intersection(ranked[:5]))
        if retrieval_k == 15:
            row["grounding_recall_at_15"] = bool(expected.intersection(ranked[:15]))
        row["explain_replay_latency_ms"] = explain_ms
        row["explain_attempts"] = explain_attempts
        write_json(args.output, {
            "schema_version": "tg-full-graphrag-corpus-v1", "corpus": args.corpus, "complete": False,
            "system": "trustgraph_full_graphrag", "rows": rows,
        })
    for index, instance in enumerate(instances, 1):
        if instance.question_id in completed:
            continue
        signature = tuple(memory.memory_id for memory in instance.memories)
        started = perf_counter()
        result, graphrag_attempts = retry_call(
            lambda: flow.graph_rag(
                query=instance.question, collection=collections[signature],
                entity_limit=20, triple_limit=20, max_subgraph_size=100,
                max_path_length=2, edge_score_limit=20, edge_limit=10,
                max_reranker_input=100,
            ),
            label=f"graph-rag:{instance.question_id}",
            max_attempts=args.max_attempts,
            initial_delay_seconds=args.retry_delay_seconds,
            max_delay_seconds=args.max_retry_delay_seconds,
        )
        latency_ms = (perf_counter() - started) * 1000
        prediction = str(result.text or "")
        mapped = source_memory_ids(list(result.sources or []), uri_to_memory)
        expected = set(instance.answer_memory_ids)
        grounded, explain_ms, explain_attempts = explain_grounding(
            instance, collections[signature]
        )
        containment = token_sequence_containment(prediction, instance.answer)
        f1 = token_f1(prediction, instance.answer)
        row = {
            "system": "trustgraph_full_graphrag",
            "question_id": instance.question_id,
            "question_type": instance.question_type,
            "question": instance.question,
            "reference": instance.answer,
            "prediction": prediction,
            "answer_memory_ids": list(instance.answer_memory_ids),
            "source_memory_ids": mapped,
            "sources": list(result.sources or []),
            "sources_mappable": bool(mapped),
            "source_recall_at_5": bool(expected.intersection(mapped[:5])) if mapped else None,
            "graphrag_grounding_memory_ids": grounded,
            "grounding_recall_at_5": bool(expected.intersection(grounded[:5])),
            "explain_replay_latency_ms": explain_ms,
            "answer_containment": containment,
            "exact_match": prediction.strip().casefold() == instance.answer.strip().casefold(),
            "token_f1": f1,
            "diagnostic_answer_score": max(f1, float(containment)),
            "full_graphrag_latency_ms": latency_ms,
            "full_graphrag_attempts": graphrag_attempts,
            "explain_attempts": explain_attempts,
            "input_tokens": int(result.in_token or 0),
            "output_tokens": int(result.out_token or 0),
            "model": result.model,
        }
        if retrieval_k == 15:
            row["source_recall_at_15"] = (
                bool(expected.intersection(mapped[:15])) if mapped else None
            )
            row["grounding_recall_at_15"] = bool(expected.intersection(grounded[:15]))
        rows.append(row)
        partial = {
            "schema_version": "tg-full-graphrag-corpus-v1", "corpus": args.corpus,
            "system": "trustgraph_full_graphrag", "complete": False,
            "examples_requested": len(instances), "collection_prefix": args.collection,
            "ingestion_submission_seconds": ingestion_submission_seconds,
            "indexing_readiness_seconds": indexing_readiness_seconds,
            "rows": rows,
        }
        write_json(args.output, partial)
        print(
            f"[{index}/{len(instances)}] score={row['diagnostic_answer_score']:.3f} "
            f"latency={latency_ms:.0f}ms sources={len(mapped)}", flush=True,
        )

    official: dict[str, Any] = {"status": "not_applicable"}
    if args.corpus == "longmemeval500":
        required = (args.official_evaluator_root, args.official_python, args.oracle_dataset)
        if any(value is None for value in required):
            parser.error("LongMemEval requires official evaluator root, Python, and oracle dataset")
        from .longmemeval_official import evaluate as evaluate_official
        official = evaluate_official(
            rows, system="trustgraph_full_graphrag_gpt4o", output=args.output,
            evaluator_root=args.official_evaluator_root,
            evaluator_python=args.official_python, oracle_dataset=args.oracle_dataset,
            judge_model=args.official_judge_model,
        )
    payload = {
        "schema_version": "tg-full-graphrag-corpus-v1", "corpus": args.corpus,
        "system": "trustgraph_full_graphrag", "complete": len(rows) == len(instances),
        "examples_requested": len(instances), "collection_prefix": args.collection,
        "unique_memories": len(memories), "bundle_count": len(signatures),
        "ingestion_submission_seconds": ingestion_submission_seconds,
        "indexing_readiness_seconds": indexing_readiness_seconds,
        "summary": summary(rows), "official_evaluation": official, "rows": rows,
        "limitations": [
            "Full GraphRAG includes TrustGraph graph traversal, reranking, prompt and synthesis.",
            "It is an end-to-end result; it does not use the shared external Phase 8.1 reader.",
            "Final-response source Recall@5 is reported only when sources map unambiguously to frozen memory IDs.",
            "Full GraphRAG grounding Recall@5 uses the ordered Exploration.entities list from an official explainability replay.",
            "Explainability replay latency is reported separately and is not added to end-to-end latency.",
            "Per-question attempt counts include retries after transient gateway or service failures.",
            "Graph-embeddings remains a separate retrieval-only ablation in the paired chart.",
        ],
    }
    write_json(args.output, payload)
    print(json.dumps(payload["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
