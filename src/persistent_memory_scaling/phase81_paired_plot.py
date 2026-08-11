"""Render the paired Phase 8.1 retrieval, quality, token, and latency chart."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/pmsb-matplotlib")


def render(
    asm: dict, trustgraph: dict, png: Path, svg: Path,
    *, hybrid: dict | None = None, full_graphrag: dict | None = None,
) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    systems = asm["systems"]
    order = ["asm_compact", "asm_hybrid", "trustgraph", "full_graphrag", "vector", "bm25"]
    labels = [
        "ASM-CM\nBridge 8.1", "ASM-CM\nHybrid",
        "TG Graph\nEmbeddings", "TG Full\nGraphRAG†",
        "Vector RAG", "BM25",
    ]
    colors = ["#55d6be", "#2ecfbd", "#ff7a90", "#ffb86c", "#7aa2f7", "#bb9af7"]
    values = {
        "asm_compact": systems["asm_compact"],
        "trustgraph": {
            "retrieval_recall": trustgraph["result"]["retrieval_recall"],
            "diagnostic_answer_score": trustgraph["result"]["diagnostic_answer_score"],
            "reader_input_tokens_total": trustgraph["result"]["reader_input_tokens_total"],
            "reader_latency_ms_mean": trustgraph["result"]["reader_latency_ms"]["mean"],
        },
        "vector": systems["vector"],
        "bm25": systems["bm25"],
    }
    if hybrid is not None:
        values["asm_hybrid"] = hybrid["summary"]["asm_vector_bm25_compact"]
    if full_graphrag is not None:
        rows = full_graphrag.get("rows", [])
        count = len(rows)
        values["full_graphrag"] = {
            "retrieval_recall": sum(bool(row.get("grounding_recall_at_5")) for row in rows) / count,
            "diagnostic_answer_score": sum(float(row["diagnostic_answer_score"]) for row in rows) / count,
            "reader_input_tokens_total": sum(int(row.get("input_tokens", 0)) for row in rows),
            "reader_latency_ms_mean": sum(float(row["full_graphrag_latency_ms"]) for row in rows) / count,
            "examples": count,
        }

    order = [key for key in order if key in values]
    labels = [label for key, label in zip(
        ["asm_compact", "asm_hybrid", "trustgraph", "full_graphrag", "vector", "bm25"], labels
    ) if key in values]
    colors = [color for key, color in zip(
        ["asm_compact", "asm_hybrid", "trustgraph", "full_graphrag", "vector", "bm25"], colors
    ) if key in values]

    plt.style.use("dark_background")
    figure, axes = plt.subplots(2, 3, figsize=(22, 11.5), constrained_layout=True)
    figure.suptitle(
        "MultiWOZ Phase 8.1 — completed systems plus TrustGraph Full GraphRAG diagnostic\n"
        "Hatched Full GraphRAG bar: n=10/979; grounding via explainability; run stopped on deterministic query failure",
        fontsize=16, weight="bold",
    )
    x = np.arange(len(order))

    axis = axes[0, 0]
    recall = [values[key]["retrieval_recall"] * 100 for key in order]
    bars = axis.bar(x, recall, color=colors)
    if "full_graphrag" in order:
        bars[order.index("full_graphrag")].set_hatch("///")
    axis.set_xticks(x, labels, fontsize=8.5)
    axis.set_ylabel("Recall@5 (%)")
    axis.set_title("Retrieval quality")
    axis.bar_label(bars, labels=[f"{value:.1f}%" for value in recall], padding=3)

    axis = axes[0, 1]
    quality = [values[key]["diagnostic_answer_score"] * 100 for key in order]
    bars = axis.bar(x, quality, color=colors)
    if "full_graphrag" in order:
        bars[order.index("full_graphrag")].set_hatch("///")
    axis.set_xticks(x, labels, fontsize=8.5)
    axis.set_ylabel("Diagnostic answer score (%)")
    axis.set_title("Answer quality")
    axis.bar_label(bars, labels=[f"{value:.1f}%" for value in quality], padding=3)

    axis = axes[0, 2]
    examples = {key: int(values[key].get("examples", 979)) for key in order}
    tokens = [values[key]["reader_input_tokens_total"] / examples[key] for key in order]
    bars = axis.bar(x, tokens, color=colors)
    if "full_graphrag" in order:
        bars[order.index("full_graphrag")].set_hatch("///")
    axis.set_xticks(x, labels, fontsize=8.5)
    axis.set_ylabel("Input tokens per question")
    axis.set_title("Context volume — Full GraphRAG reports internal input")
    axis.bar_label(bars, labels=[f"{value:,.0f}" for value in tokens], padding=3)

    axis = axes[1, 1]
    latency_order = [key for key in ("asm_compact", "trustgraph", "full_graphrag") if key in values]
    latency_labels = {
        "asm_compact": "ASM-CM + Bridge\noperational E2E",
        "trustgraph": "TG graph-embeddings\nretrieval + reader",
        "full_graphrag": "TG Full GraphRAG\nE2E (n=10)",
    }
    latency_values = {
        "asm_compact": trustgraph["comparison_to_asm_operational"]["asm_mean_from_total_duration_ms"],
        "trustgraph": trustgraph["result"]["combined_latency_ms"]["mean"],
        "full_graphrag": values.get("full_graphrag", {}).get("reader_latency_ms_mean", 0),
    }
    lx = np.arange(len(latency_order))
    latency = [latency_values[key] for key in latency_order]
    latency_colors = [colors[order.index(key)] for key in latency_order]
    bars = axis.bar(lx, latency, color=latency_colors)
    if "full_graphrag" in latency_order:
        bars[latency_order.index("full_graphrag")].set_hatch("///")
    axis.set_xticks(lx, [latency_labels[key] for key in latency_order])
    axis.set_ylabel("Observed mean latency (ms/question)")
    axis.set_title("Operational latency — path definitions shown")
    axis.bar_label(bars, labels=[f"{value:.0f}" for value in latency], padding=3)

    axis = axes[1, 0]
    completion_order = ["asm_compact", "asm_hybrid", "trustgraph", "full_graphrag"]
    completion_order = [key for key in completion_order if key in values]
    completed = [examples[key] for key in completion_order]
    cx = np.arange(len(completion_order))
    completion_labels = [labels[order.index(key)] for key in completion_order]
    completion_colors = [colors[order.index(key)] for key in completion_order]
    bars = axis.bar(cx, completed, color=completion_colors)
    if "full_graphrag" in completion_order:
        bars[completion_order.index("full_graphrag")].set_hatch("///")
    axis.set_xticks(cx, completion_labels)
    axis.set_ylabel("Questions completed (of 979)")
    axis.set_title("Protocol completion")
    axis.set_ylim(0, 1080)
    axis.bar_label(bars, labels=[f"{value}/979" for value in completed], padding=3)

    axis = axes[1, 2]
    axis.axis("off")
    axis.set_title("Measurement boundaries", weight="bold")
    axis.text(
        0.02, 0.94,
        "COMPLETED (n=979)\n"
        "• ASM-CM + Bridge 8.1\n"
        "• ASM-CM hybrid Vector + BM25\n"
        "• TrustGraph graph-embeddings\n"
        "• Vector RAG and BM25 controls\n\n"
        "DIAGNOSTIC ONLY (n=10)\n"
        "• TrustGraph Full GraphRAG bounded\n"
        "• 0/10 final-response sources mappable\n"
        "• query 11 failed identically in 2/2 isolated attempts\n"
        "• not promoted to the 979-question comparison\n\n"
        "SEPARATE LONGMEMEVAL SETUP INCIDENT\n"
        "• 119 collection registrations succeeded\n"
        "• collection 120 stalled 600 s → HTTP 504\n"
        "• paced, resumable setup reached 500/500\n\n"
        "Full GraphRAG Recall@5 is grounding from a separate\n"
        "official explainability replay, not final-response sources.",
        transform=axis.transAxes, va="top", fontsize=11, linespacing=1.35,
        bbox={"boxstyle": "round,pad=.7", "facecolor": "#151922", "edgecolor": "#666"},
    )

    for axis in axes.flat:
        axis.grid(axis="y", alpha=.2)
        axis.set_axisbelow(True)
    png.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(png, dpi=180)
    figure.savefig(svg)
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asm", type=Path, required=True)
    parser.add_argument("--trustgraph", type=Path, required=True)
    parser.add_argument("--hybrid", type=Path)
    parser.add_argument("--full-graphrag", type=Path)
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()
    render(
        json.loads(args.asm.read_text()), json.loads(args.trustgraph.read_text()),
        args.png, args.svg,
        hybrid=json.loads(args.hybrid.read_text()) if args.hybrid else None,
        full_graphrag=(
            json.loads(args.full_graphrag.read_text()) if args.full_graphrag else None
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
