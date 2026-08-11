"""Plot LongMemEval-S answer accuracy against measured reader-context consumption."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/pmsb-matplotlib")

ORDER = [
    "asm_bridge81_gpt4o",
    "vector_bridge81_gpt4o",
    "bm25_bridge81_gpt4o",
    "asm_vector_rrf_bridge81_gpt4o",
    "asm_bm25_rrf_bridge81_gpt4o",
    "vector_bm25_rrf_bridge81_gpt4o",
    "asm_vector_bm25_rrf_bridge81_gpt4o",
    "trustgraph_graph_embeddings_gpt4o",
]
LABELS = {
    "asm_bridge81_gpt4o": "ASM-CM + Bridge",
    "vector_bridge81_gpt4o": "Vector + Bridge",
    "bm25_bridge81_gpt4o": "BM25 + Bridge",
    "asm_vector_rrf_bridge81_gpt4o": "ASM + Vector RRF",
    "asm_bm25_rrf_bridge81_gpt4o": "ASM + BM25 RRF",
    "vector_bm25_rrf_bridge81_gpt4o": "Vector + BM25 RRF",
    "asm_vector_bm25_rrf_bridge81_gpt4o": "ASM + Vector + BM25 RRF",
    "trustgraph_graph_embeddings_gpt4o": "TrustGraph graph-embeddings\n(uncompacted)",
}
COLORS = ["#55d6be", "#2dd4bf", "#f6c85f", "#7aa2f7", "#bb9af7", "#ff7a90", "#ff9e64", "#f7768e"]
ANNOTATION_OFFSETS = {
    "asm_bridge81_gpt4o": (5, 5),
    "vector_bridge81_gpt4o": (5, 16),
    "bm25_bridge81_gpt4o": (5, -7),
    "asm_vector_rrf_bridge81_gpt4o": (5, 5),
    "asm_bm25_rrf_bridge81_gpt4o": (5, -10),
    "vector_bm25_rrf_bridge81_gpt4o": (5, 29),
    "asm_vector_bm25_rrf_bridge81_gpt4o": (5, 5),
    "trustgraph_graph_embeddings_gpt4o": (5, 5),
}


def measurements(asm: dict[str, Any], trustgraph: dict[str, Any]) -> dict[str, dict[str, float]]:
    summary = dict(asm["summary"])
    official = dict(asm["official_evaluation"]["results"])
    key = "trustgraph_graph_embeddings_gpt4o"
    summary[key] = trustgraph["summary"]
    official[key] = trustgraph["official_evaluation"]["results"][key]
    return {
        system: {
            "tokens": float(summary[system]["reader_input_tokens_mean"]),
            "accuracy": float(official[system]["accuracy"]) * 100,
        }
        for system in ORDER
    }


def render(data: dict[str, dict[str, float]], png: Path, svg: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.style.use("dark_background")
    figure, axes = plt.subplots(1, 3, figsize=(21, 7.5), constrained_layout=True)
    figure.suptitle(
        "LongMemEval-S — official accuracy versus reader-context consumption\n"
        "Same 500 questions and GPT-4o judge; TrustGraph point is uncompacted",
        fontsize=16, weight="bold",
    )

    tokens = [data[key]["tokens"] for key in ORDER]
    accuracy = [data[key]["accuracy"] for key in ORDER]
    for key, color in zip(ORDER, COLORS, strict=True):
        axes[0].scatter(data[key]["tokens"], data[key]["accuracy"], s=105, color=color)
        axes[0].annotate(
            LABELS[key], (data[key]["tokens"], data[key]["accuracy"]),
            xytext=ANNOTATION_OFFSETS[key], textcoords="offset points", fontsize=8,
        )
    axes[0].set_xscale("log")
    axes[0].set_xlabel("Mean reader input tokens per question (log scale)")
    axes[0].set_ylabel("Official GPT-4o judge accuracy (%)")
    axes[0].set_title("Absolute consumption vs. accuracy")

    baseline = data["asm_bridge81_gpt4o"]
    delta_tokens = [data[key]["tokens"] - baseline["tokens"] for key in ORDER[1:]]
    delta_accuracy = [data[key]["accuracy"] - baseline["accuracy"] for key in ORDER[1:]]
    for key, color, dx, dy in zip(ORDER[1:], COLORS[1:], delta_tokens, delta_accuracy, strict=True):
        axes[1].scatter(dx, dy, s=105, color=color)
        axes[1].annotate(
            LABELS[key], (dx, dy), xytext=ANNOTATION_OFFSETS[key],
            textcoords="offset points", fontsize=8,
        )
    axes[1].axhline(0, color="#888", linewidth=.8)
    axes[1].axvline(0, color="#888", linewidth=.8)
    axes[1].set_xscale("symlog", linthresh=50)
    axes[1].set_xlabel("Δ input tokens/question vs. ASM-CM + Bridge (symlog)")
    axes[1].set_ylabel("Δ official accuracy (percentage points)")
    axes[1].set_title("Accuracy gain versus additional context")

    efficiency = [data[key]["accuracy"] / (data[key]["tokens"] / 1000) for key in ORDER]
    bars = axes[2].barh(range(len(ORDER)), efficiency, color=COLORS)
    axes[2].set_yticks(range(len(ORDER)), [LABELS[key] for key in ORDER])
    axes[2].invert_yaxis()
    axes[2].set_xlabel("Official accuracy points per 1K input tokens")
    axes[2].set_title("Context efficiency")
    axes[2].bar_label(bars, labels=[f"{value:.1f}" for value in efficiency], padding=3, fontsize=8)

    for axis in axes:
        axis.grid(alpha=.18)
        axis.set_axisbelow(True)
    figure.patch.set_facecolor("#090b10")
    png.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(png, dpi=190, facecolor=figure.get_facecolor())
    figure.savefig(svg, facecolor=figure.get_facecolor())
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asm", type=Path, required=True)
    parser.add_argument("--trustgraph", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()
    asm = json.loads(args.asm.read_text(encoding="utf-8"))
    trustgraph = json.loads(args.trustgraph.read_text(encoding="utf-8"))
    render(measurements(asm, trustgraph), args.png, args.svg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
