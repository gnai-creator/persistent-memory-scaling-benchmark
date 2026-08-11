"""Official LongMemEval judge adapter for completed TrustGraph predictions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(
    rows: list[dict[str, Any]], *, system: str, output: Path,
    evaluator_root: Path, evaluator_python: Path, oracle_dataset: Path,
    judge_model: str = "gpt-4o",
) -> dict[str, Any]:
    from benchmarks.longmemeval.phase4 import run_official_evaluator

    output_root = output.parent / f"{output.stem}-official"
    hypothesis = output_root / "hypotheses" / f"{system}.jsonl"
    hypothesis.parent.mkdir(parents=True, exist_ok=True)
    hypothesis.write_text("".join(
        json.dumps({"question_id": row["question_id"], "hypothesis": row["prediction"]}) + "\n"
        for row in sorted(rows, key=lambda item: str(item["question_id"]))
    ), encoding="utf-8")
    results = run_official_evaluator(
        evaluator_root.resolve(), {system: str(hypothesis.resolve())},
        oracle_dataset.resolve(), judge_model=judge_model,
        python_bin=str(evaluator_python), output_root=output_root,
    )
    return {"status": "completed", "results": results, "hypothesis": str(hypothesis)}
