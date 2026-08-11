"""Render the paired Phase 8.1 retrieval, quality, token, and latency chart."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/pmsb-matplotlib")


def render(asm: dict, trustgraph: dict, png: Path, svg: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    systems = asm["systems"]
    order = ["asm_compact", "trustgraph", "vector", "bm25"]
    labels = ["ASM-CM +\nBridge 8.1", "TrustGraph\ngraph-embeddings", "Vector RAG", "BM25"]
    colors = ["#55d6be", "#ff7a90", "#7aa2f7", "#bb9af7"]
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

    plt.style.use("dark_background")
    figure, axes = plt.subplots(2, 2, figsize=(15, 9), constrained_layout=True)
    figure.suptitle(
        "Paired MultiWOZ Phase 8.1 — same 979 questions and Qwen3 14B reader\n"
        "TrustGraph result uses graph-embeddings retrieval, not full GraphRAG",
        fontsize=16, weight="bold",
    )
    x = np.arange(len(order))

    axis = axes[0, 0]
    recall = [values[key]["retrieval_recall"] * 100 for key in order]
    bars = axis.bar(x, recall, color=colors)
    axis.set_xticks(x, labels)
    axis.set_ylabel("Recall@5 (%)")
    axis.set_title("Retrieval quality")
    axis.bar_label(bars, labels=[f"{value:.1f}%" for value in recall], padding=3)

    axis = axes[0, 1]
    quality = [values[key]["diagnostic_answer_score"] * 100 for key in order]
    bars = axis.bar(x, quality, color=colors)
    axis.set_xticks(x, labels)
    axis.set_ylabel("Diagnostic answer score (%)")
    axis.set_title("Answer quality")
    axis.bar_label(bars, labels=[f"{value:.1f}%" for value in quality], padding=3)

    axis = axes[1, 0]
    tokens = [values[key]["reader_input_tokens_total"] / 1e6 for key in order]
    bars = axis.bar(x, tokens, color=colors)
    axis.set_xticks(x, labels)
    axis.set_ylabel("Reader input tokens (millions)")
    axis.set_title("Measured reader context")
    axis.bar_label(bars, labels=[f"{value:.2f}M" for value in tokens], padding=3)

    axis = axes[1, 1]
    latency = [values[key]["reader_latency_ms_mean"] for key in order]
    bars = axis.bar(x, latency, color=colors)
    axis.set_xticks(x, labels)
    axis.set_ylabel("Mean reader latency (ms)")
    axis.set_title("Reader only — runtime conditions differ")
    axis.bar_label(bars, labels=[f"{value:.0f}" for value in latency], padding=3)
    axis.text(
        .98, .95, "TrustGraph retrieval adds 178.5 ms mean\nASM uses frozen retrieval replay",
        transform=axis.transAxes, ha="right", va="top", fontsize=8, color="#b7b7b7",
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
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()
    render(json.loads(args.asm.read_text()), json.loads(args.trustgraph.read_text()),
           args.png, args.svg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
