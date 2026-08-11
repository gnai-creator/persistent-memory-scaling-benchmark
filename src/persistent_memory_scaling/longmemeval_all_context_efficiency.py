"""Compare history consumption and answer accuracy across completed LongMemEval systems."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

import tiktoken


TG_KEY = "trustgraph_graph_embeddings_gpt4o"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asm-root", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--asm-results", type=Path, required=True)
    parser.add_argument("--trustgraph-results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path[:0] = [str(args.asm_root), str(args.asm_root / "src")]
    from asm_memory_bridge import (
        ContextAssembler, ExtractiveCompactor, InMemoryPayloadStore,
        LabelAuthorizationPolicy, RetrievalCandidate,
    )
    from benchmarks.longmemeval.adapter import load_dataset

    encoding = tiktoken.get_encoding("o200k_base")
    instances = {item.question_id: item for item in load_dataset(args.dataset)}
    histories: dict[str, dict[str, int]] = {}
    for instance in instances.values():
        text = "\n\n".join(memory.content for memory in instance.memories)
        histories[instance.question_id] = {
            "bytes": len(text.encode("utf-8")),
            "tokens": len(encoding.encode(text, disallowed_special=())),
            "memories": len(instance.memories),
        }
    asm = json.loads(args.asm_results.read_text(encoding="utf-8"))
    tg = json.loads(args.trustgraph_results.read_text(encoding="utf-8"))
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in asm["rows"]:
        grouped[str(row["system"])].append(row)
    for row in tg["rows"]:
        grouped[TG_KEY].append(row)
    official = dict(asm["official_evaluation"]["results"])
    official[TG_KEY] = tg["official_evaluation"]["results"][TG_KEY]
    compactor_config = asm["protocol"]["compactor"]
    compactor = ExtractiveCompactor(
        max_total_bytes=int(compactor_config["max_total_bytes"]),
        max_bytes_per_memory=int(compactor_config["max_bytes_per_memory"]),
        max_anchors_per_memory=int(compactor_config["max_anchors_per_memory"]),
        window_radius=int(compactor_config["window_radius"]),
    )

    def evidence_content(row: dict[str, Any], *, compact: bool) -> str:
        instance = instances[str(row["question_id"])]
        store = InMemoryPayloadStore()
        for memory in instance.memories:
            store.put(memory)
        policy = LabelAuthorizationPolicy()
        policy.authorize_query(instance.query)
        candidates = tuple(RetrievalCandidate(
            memory_id=str(memory_id), score=1.0 / rank, rank=rank,
            retrieval_reason="frozen ranking replay for accounting",
        ) for rank, memory_id in enumerate(row["retrieved_memory_ids"], 1))
        package = ContextAssembler(
            max_context_bytes=int(asm["protocol"]["max_context_bytes"])
        ).assemble(instance.query, candidates, store, policy)
        if compact:
            package = compactor.compact(instance.query, package)
        if tuple(row["evidence_memory_ids"]) != tuple(item.memory_id for item in package.evidence):
            raise ValueError(f"evidence ID replay mismatch for {row['system']}/{row['question_id']}")
        content = "\n\n".join(item.content for item in package.evidence)
        if len(content.encode("utf-8")) != int(row["evidence_bytes"]):
            raise ValueError(f"evidence byte replay mismatch for {row['system']}/{row['question_id']}")
        return content

    systems: dict[str, Any] = {}
    for system, rows in grouped.items():
        accuracy = float(official[system]["accuracy"]) * 100
        input_mean = mean(float(row["reader_input_tokens"]) for row in rows)
        evidence_tokens = [
            len(encoding.encode(
                evidence_content(row, compact=system != TG_KEY), disallowed_special=()
            ))
            for row in rows
        ]
        evidence_fraction = mean(
            float(row["evidence_bytes"]) / histories[str(row["question_id"])]["bytes"]
            for row in rows
        )
        reader_history_ratio = mean(
            float(row["reader_input_tokens"]) / histories[str(row["question_id"])]["tokens"]
            for row in rows
        )
        memory_fraction = mean(
            len(row["evidence_memory_ids"]) / histories[str(row["question_id"])]["memories"]
            for row in rows
        )
        evidence_token_fraction = mean(
            tokens / histories[str(row["question_id"])]["tokens"]
            for tokens, row in zip(evidence_tokens, rows, strict=True)
        )
        systems[system] = {
            "examples": len(rows),
            "official_accuracy_percent": accuracy,
            "reader_input_tokens_mean": input_mean,
            "evidence_tokens_o200k_mean": mean(evidence_tokens),
            "history_fraction_consumed": evidence_token_fraction,
            "evidence_history_byte_fraction": evidence_fraction,
            "reader_input_to_history_content_token_ratio": reader_history_ratio,
            "included_memory_fraction": memory_fraction,
            "reader_latency_ms_mean": mean(float(row["reader_latency_ms"]) for row in rows),
            "accuracy_points_per_1k_reader_tokens": accuracy / (input_mean / 1000),
            "reader_tokens_per_accuracy_point": input_mean / accuracy if accuracy else None,
        }
    result = {
        "protocol": {
            "dataset": str(args.dataset.resolve()),
            "tokenizer": "o200k_base",
            "evidence_history_byte_fraction": "exact evidence bytes divided by complete history bytes",
            "history_fraction_consumed": "evidence content o200k_base tokens divided by complete history content tokens",
            "reader_input_to_history_content_token_ratio": (
                "provider-reported complete prompt tokens divided by complete history content tokens; "
                "includes prompt/provenance overhead and is not an evidence-only fraction"
            ),
            "trustgraph_classification": "uncompacted graph-embeddings ablation",
        },
        "systems": systems,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(systems, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
