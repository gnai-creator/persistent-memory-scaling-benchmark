"""Measure how much LongMemEval history reached the uncompacted TrustGraph reader."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean, median
from typing import Any

import tiktoken


def summarize(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "mean": mean(values),
        "median": median(values),
        "p95": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
        "min": ordered[0],
        "max": ordered[-1],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asm-root", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--trustgraph-results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path[:0] = [str(args.asm_root), str(args.asm_root / "src")]
    from benchmarks.longmemeval.adapter import load_dataset

    encoding = tiktoken.get_encoding("o200k_base")
    instances = {item.question_id: item for item in load_dataset(args.dataset)}
    payload = json.loads(args.trustgraph_results.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for source in payload["rows"]:
        instance = instances[str(source["question_id"])]
        memories = {memory.memory_id: memory for memory in instance.memories}
        total_text = "\n\n".join(memory.content for memory in instance.memories)
        selected = [memories[mid].content for mid in source["evidence_memory_ids"] if mid in memories]
        selected_text = "\n\n".join(selected)
        total_bytes = len(total_text.encode("utf-8"))
        total_tokens = len(encoding.encode(total_text, disallowed_special=()))
        selected_tokens = len(encoding.encode(selected_text, disallowed_special=()))
        rows.append({
            "question_id": instance.question_id,
            "available_memories": len(instance.memories),
            "included_memories": len(source["evidence_memory_ids"]),
            "included_memory_fraction": len(source["evidence_memory_ids"]) / len(instance.memories),
            "available_history_bytes": total_bytes,
            "reader_evidence_bytes": int(source["evidence_bytes"]),
            "evidence_byte_fraction": int(source["evidence_bytes"]) / total_bytes,
            "available_history_tokens_o200k": total_tokens,
            "selected_content_tokens_o200k": selected_tokens,
            "selected_token_fraction": selected_tokens / total_tokens,
            "provider_reader_input_tokens": int(source["reader_input_tokens"]),
        })
    result = {
        "protocol": {
            "source": str(args.trustgraph_results.resolve()),
            "source_classification": "TrustGraph graph-embeddings uncompacted ablation",
            "tokenizer": "o200k_base",
            "evidence_byte_fraction_is_exact": True,
            "selected_token_fraction_definition": "raw contents of evidence_memory_ids / all history contents",
            "provider_input_includes_prompt_and_provenance_overhead": True,
        },
        "examples": len(rows),
        "summary": {
            "available_memories": summarize([row["available_memories"] for row in rows]),
            "included_memories": summarize([row["included_memories"] for row in rows]),
            "included_memory_fraction": summarize([row["included_memory_fraction"] for row in rows]),
            "evidence_byte_fraction": summarize([row["evidence_byte_fraction"] for row in rows]),
            "available_history_tokens_o200k": summarize([row["available_history_tokens_o200k"] for row in rows]),
            "selected_content_tokens_o200k": summarize([row["selected_content_tokens_o200k"] for row in rows]),
            "selected_token_fraction": summarize([row["selected_token_fraction"] for row in rows]),
            "provider_reader_input_tokens": summarize([row["provider_reader_input_tokens"] for row in rows]),
        },
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
