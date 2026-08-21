"""Validate paired ASM/RAG rows and render the comparative chart."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .asm_reader_context_scaling_runner import _load_jsonl, _sha256, _write_json
from .reader_context_scaling import aggregate, render

QUALITY_FLOORS = {"recall_at_5": 0.90, "qa_score": 0.65}


def validate_pair(asm_rows: list[dict[str, Any]], rag_rows: list[dict[str, Any]]) -> None:
    if not asm_rows or not rag_rows:
        raise ValueError("both ASM and RAG observations are required")
    asm_keys = {(int(row["history_events"]), str(row["query_id"])) for row in asm_rows}
    rag_keys = {(int(row["history_events"]), str(row["query_id"])) for row in rag_rows}
    if asm_keys != rag_keys:
        raise ValueError("ASM and RAG must contain the same checkpoint/query pairs")
    readers = {str(row["reader_model"]) for row in asm_rows + rag_rows}
    if len(readers) != 1:
        raise ValueError("ASM and RAG must use the same reader model")


def quality_gates(summary: dict[str, Any]) -> list[dict[str, Any]]:
    systems = {point["system"] for point in summary["points"]}
    gates = []
    for checkpoint in sorted({int(point["history_events"]) for point in summary["points"]}):
        selected = [point for point in summary["points"] if int(point["history_events"]) == checkpoint]
        passed = len(selected) == len(systems) and all(
            point[metric] >= floor for point in selected
            for metric, floor in QUALITY_FLOORS.items()
        )
        gates.append({"history_events": checkpoint, "passed": passed,
                      "economic_comparison_authorized": passed})
    return gates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asm", type=Path, required=True)
    parser.add_argument("--rag", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()
    asm_rows, rag_rows = _load_jsonl(args.asm), _load_jsonl(args.rag)
    validate_pair(asm_rows, rag_rows)
    result = aggregate(asm_rows + rag_rows)
    if max(int(row["history_events"]) for row in asm_rows + rag_rows) < 10_000:
        result["measurement_status"] = "measured-integration-smoke"
    result["comparison_status"] = "paired-measured"
    result["pairing"] = {"same_checkpoint_queries": True, "same_reader": True,
                         "asm_sha256": _sha256(args.asm), "rag_sha256": _sha256(args.rag)}
    result["quality_floor"] = QUALITY_FLOORS
    result["quality_gates"] = quality_gates(result)
    _write_json(args.summary, result)
    render(result, args.png, args.svg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
