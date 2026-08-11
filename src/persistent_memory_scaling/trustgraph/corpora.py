"""Deterministic corpus adapters shared by final TrustGraph runners."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_instances(
    corpus: str,
    *,
    asm_root: Path,
    frozen_results: Path,
    multiwoz_root: Path | None = None,
    dataset: Path | None = None,
    retrieval_root: Path | None = None,
) -> tuple[list[Any], dict[str, Any]]:
    """Return ordered instances and the frozen external-reader protocol."""
    import sys

    sys.path[:0] = [str(asm_root), str(asm_root / "src")]
    frozen = json.loads(frozen_results.read_text(encoding="utf-8"))

    if corpus == "multiwoz979":
        if multiwoz_root is None:
            raise ValueError("multiwoz979 requires --multiwoz-root")
        from benchmarks.multiwoz.adapter import load_multiwoz

        ids = [str(value) for value in frozen["protocol"]["evaluation_question_ids"]]
        loaded = load_multiwoz(
            multiwoz_root, "test", bundle_size=16,
            maximum=int(frozen["protocol"]["source_evaluation_examples"]),
        )
        by_id = {item.question_id: item for item in loaded}
        return [by_id[value] for value in ids], dict(frozen["protocol"])

    if corpus == "longmemeval500":
        if dataset is None:
            raise ValueError("longmemeval500 requires --dataset")
        from benchmarks.longmemeval.adapter import load_dataset

        ids = [str(value) for value in frozen["protocol"]["evaluation_question_ids"]]
        if len(ids) != 500:
            raise ValueError(f"LongMemEval frozen result has {len(ids)} IDs, expected 500")
        by_id = {item.question_id: item for item in load_dataset(dataset)}
        return [by_id[value] for value in ids], dict(frozen["protocol"])

    if corpus == "free128":
        if retrieval_root is None:
            raise ValueError("free128 requires --retrieval-root")
        from benchmarks.dual_asm.r2 import frozen_stratified_sample
        from benchmarks.dual_asm.r05 import deterministic_pool
        from benchmarks.dual_asm.r32 import as_instance, load_reference_answers
        from benchmarks.dual_asm.weak_supervision import add_fallback_negatives, jsonl, load_rows

        ids = [str(value) for value in frozen["protocol"]["evaluation_ids"]]
        if len(ids) != 128:
            raise ValueError(f"R3.2 frozen result has {len(ids)} IDs, expected 128")
        rows = load_rows(retrieval_root, "test", include_share_alike=False, maximum=0)
        add_fallback_negatives(rows)
        selected = frozen_stratified_sample(rows, 128)
        if [row["example_id"] for row in selected] != ids:
            raise ValueError("free-language source rows differ from frozen R3.2 IDs")
        answers = load_reference_answers(retrieval_root)
        memory_rows = [
            row for row in jsonl(retrieval_root / "memories.jsonl")
            if row.get("commercial_partition") == "permissive"
        ]
        memory_content = {row["memory_id"]: row["content"] for row in memory_rows}
        universe = sorted(row["memory_id"] for row in memory_rows if row.get("split") == "test")
        for row in selected:
            row["reference_answer"] = answers[row["example_id"]]
            row["candidate_ids"] = deterministic_pool(row, universe, 128)
        # R3.2 used the Phase 8.1 reader protocol; it is embedded under reader_protocol
        # when available. Wrappers otherwise pass the promoted Phase-8 result separately.
        protocol = dict(frozen["protocol"].get("reader_protocol", {}))
        return [as_instance(row, memory_content) for row in selected], protocol

    raise ValueError(f"unsupported corpus: {corpus}")
