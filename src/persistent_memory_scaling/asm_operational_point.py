"""Extract and plot a measured ASM Memory Bridge operational point."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from statistics import fmean
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/pmsb-matplotlib")

from .reader_context_scaling import percentile


def extract(source: dict[str, Any], source_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = source.get("rows", [])
    if not rows:
        raise ValueError("source contains no query rows")
    systems = {str(row.get("system")) for row in rows}
    if len(systems) != 1 or not systems.issubset({"asm_compact", "asm", "ASM Memory Bridge"}):
        raise ValueError(f"expected one ASM-only system, found {sorted(systems)}")

    observations = []
    for index, row in enumerate(rows):
        required = ("question_id", "reader_input_tokens", "retrieval_recall", "diagnostic_answer_score")
        missing = [key for key in required if key not in row]
        if missing:
            raise ValueError(f"row {index} is missing: {', '.join(missing)}")
        observations.append({
            "system": "ASM Memory Bridge",
            "workload": "MultiWOZ Phase 8.1",
            "question_id": row["question_id"],
            "reader_context_tokens": int(row["reader_input_tokens"]),
            "recall_at_5": float(row["retrieval_recall"]),
            "qa_score": float(row["diagnostic_answer_score"]),
        })

    tokens = [float(row["reader_context_tokens"]) for row in observations]
    summary = {
        "schema_version": "asm-operational-point-summary-v1",
        "measurement_status": "measured-single-operational-point",
        "system": "ASM Memory Bridge",
        "workload": "MultiWOZ Phase 8.1",
        "n": len(observations),
        "reader_context_tokens": {
            "mean": fmean(tokens),
            "p50": percentile(tokens, .50),
            "p95": percentile(tokens, .95),
            "p99": percentile(tokens, .99),
            "total": sum(tokens),
        },
        "recall_at_5": fmean(row["recall_at_5"] for row in observations),
        "qa_score": fmean(row["qa_score"] for row in observations),
        "provenance": {
            "source": str(source_path),
            "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
            "dataset_sha256": source.get("protocol", {}).get("dataset_sha256"),
            "reader": source.get("protocol", {}).get("reader"),
            "frozen_evaluation_examples": source.get("protocol", {}).get("frozen_evaluation_examples"),
        },
        "limitation": "One measured workload point; this is not a 10k/100k/1M history-scaling curve.",
    }
    return observations, summary


def render(summary: dict[str, Any], png: Path, svg: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.style.use("dark_background")
    figure, axes = plt.subplots(1, 2, figsize=(13, 6), constrained_layout=True)
    figure.suptitle(
        f"ASM Memory Bridge — measured Phase 8.1 operational point (n={summary['n']})\n"
        "SINGLE POINT — NOT A HISTORY-SCALING CURVE",
        fontsize=16, weight="bold",
    )
    context = summary["reader_context_tokens"]
    labels = ["p50", "mean", "p95", "p99"]
    values = [context[key] for key in labels]
    bars = axes[0].bar(labels, values, color=("#55d6be", "#7aa2f7", "#ffca5c", "#f7768e"))
    axes[0].bar_label(bars, labels=[f"{value:,.0f}" for value in values], padding=3)
    axes[0].set_title("Measured reader-context distribution")
    axes[0].set_ylabel("Input tokens per question")
    axes[0].set_ylim(0, max(values) * 1.18)

    quality_labels = ["Recall@5", "QA score"]
    quality = [100 * summary["recall_at_5"], 100 * summary["qa_score"]]
    quality_bars = axes[1].bar(quality_labels, quality, color=("#55d6be", "#bb9af7"))
    axes[1].bar_label(quality_bars, labels=[f"{value:.1f}%" for value in quality], padding=3)
    axes[1].set_title("Quality adjacent to token consumption")
    axes[1].set_ylabel("Quality (%)")
    axes[1].set_ylim(0, 105)
    for axis in axes:
        axis.grid(axis="y", alpha=.2)
    png.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(png, dpi=180)
    figure.savefig(svg)
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--jsonl", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    observations, summary = extract(source, args.source)
    args.jsonl.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.jsonl.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in observations), encoding="utf-8")
    args.summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    render(summary, args.png, args.svg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
