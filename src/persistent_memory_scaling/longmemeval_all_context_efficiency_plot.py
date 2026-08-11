"""Plot LongMemEval context consumption against official answer accuracy."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/pmsb-matplotlib")

ORDER = [
    "asm_bridge81_gpt4o", "asm_vector_rrf_bridge81_gpt4o",
    "asm_bm25_rrf_bridge81_gpt4o", "asm_vector_bm25_rrf_bridge81_gpt4o",
    "vector_bridge81_gpt4o", "bm25_bridge81_gpt4o",
    "vector_bm25_rrf_bridge81_gpt4o", "trustgraph_graph_embeddings_gpt4o",
]
LABELS = {
    "asm_bridge81_gpt4o": "ASM-CM + Bridge",
    "asm_vector_rrf_bridge81_gpt4o": "ASM + Vector RRF",
    "asm_bm25_rrf_bridge81_gpt4o": "ASM + BM25 RRF",
    "asm_vector_bm25_rrf_bridge81_gpt4o": "ASM + Vector + BM25 RRF",
    "vector_bridge81_gpt4o": "Vector + Bridge",
    "bm25_bridge81_gpt4o": "BM25 + Bridge",
    "vector_bm25_rrf_bridge81_gpt4o": "Vector + BM25 RRF",
    "trustgraph_graph_embeddings_gpt4o": "TrustGraph graph-embeddings\n(uncompacted)",
}
COLORS = ["#55d6be", "#7aa2f7", "#bb9af7", "#ff9e64", "#2dd4bf", "#f6c85f", "#ff7a90", "#f7768e"]


def render(payload: dict, png: Path, svg: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = payload["systems"]
    plt.style.use("dark_background")
    figure, axes = plt.subplots(3, 2, figsize=(18, 15), constrained_layout=True)
    figure.suptitle(
        "LongMemEval-S — history consumption versus official answer accuracy\n"
        "Completed 500-question runs; TrustGraph point is uncompacted",
        fontsize=16, weight="bold",
    )
    figure.text(
        .5, .935,
        "2k diagnostic disclaimer — Primary retrieval failure: correct evidence ranked too low for the 2k budget. "
        "Secondary reader failure: GPT-4o failed to abstain and hallucinated both the answer and citation.",
        ha="center", fontsize=9, color="#c9ced8",
    )
    figure.text(
        .5, .916,
        "Grounding safeguard success: the reader hallucinated an unsupported answer and a nonexistent citation ID, "
        "but the Bridge rejected the response before user delivery.",
        ha="center", fontsize=9, color="#55d6be", weight="bold",
    )
    figure.get_layout_engine().set(rect=(0, 0, 1, .89))
    labels = [LABELS[key] for key in ORDER]
    coverage = [100 * data[key]["history_fraction_consumed"] for key in ORDER]
    memory_fraction = [100 * data[key]["included_memory_fraction"] for key in ORDER]
    accuracy = [data[key]["official_accuracy_percent"] for key in ORDER]
    efficiency = [data[key]["accuracy_points_per_1k_reader_tokens"] for key in ORDER]
    tokens_per_point = [data[key]["reader_tokens_per_accuracy_point"] for key in ORDER]

    bars = axes[0, 0].barh(range(len(ORDER)), coverage, color=COLORS)
    axes[0, 0].set_yticks(range(len(ORDER)), labels)
    axes[0, 0].invert_yaxis()
    axes[0, 0].bar_label(bars, labels=[f"{value:.1f}%" for value in coverage], padding=3)
    axes[0, 0].set_xlabel("Evidence tokens / available history tokens")
    axes[0, 0].set_title("History fraction consumed")

    bars = axes[0, 1].barh(range(len(ORDER)), memory_fraction, color=COLORS)
    axes[0, 1].set_yticks(range(len(ORDER)), labels)
    axes[0, 1].invert_yaxis()
    axes[0, 1].bar_label(bars, labels=[f"{value:.1f}%" for value in memory_fraction], padding=3)
    axes[0, 1].set_xlabel("Included memories / available memories")
    axes[0, 1].set_title("Memory fraction selected")

    for key, color in zip(ORDER, COLORS, strict=True):
        item = data[key]
        axes[1, 0].scatter(
            100 * item["history_fraction_consumed"], item["official_accuracy_percent"],
            s=105, color=color, label=LABELS[key].replace("\n", " "),
        )
    axes[1, 0].set_xlabel("History tokens delivered as evidence (%)")
    axes[1, 0].set_ylabel("Official GPT-4o judge accuracy (%)")
    axes[1, 0].set_title("Accuracy–context Pareto view")
    axes[1, 0].legend(fontsize=7, loc="center left", bbox_to_anchor=(1.01, .5))

    bars = axes[1, 1].barh(range(len(ORDER)), efficiency, color=COLORS)
    axes[1, 1].set_yticks(range(len(ORDER)), labels)
    axes[1, 1].invert_yaxis()
    axes[1, 1].bar_label(bars, labels=[f"{value:.1f}" for value in efficiency], padding=3)
    axes[1, 1].set_xlabel("Official accuracy points per 1K reader input tokens")
    axes[1, 1].set_title("Reader-context efficiency — higher is better")
    axes[1, 1].margins(x=.12)

    bars = axes[2, 0].barh(range(len(ORDER)), tokens_per_point, color=COLORS)
    axes[2, 0].set_yticks(range(len(ORDER)), labels)
    axes[2, 0].invert_yaxis()
    axes[2, 0].bar_label(bars, labels=[f"{value:.0f}" for value in tokens_per_point], padding=3)
    axes[2, 0].set_xlabel("Mean reader input tokens per official accuracy point")
    axes[2, 0].set_title("Context cost of accuracy — lower is better")
    axes[2, 0].margins(x=.12)

    for key, color in zip(ORDER, COLORS, strict=True):
        item = data[key]
        axes[2, 1].scatter(
            item["reader_latency_ms_mean"] / 1000, item["official_accuracy_percent"],
            s=105, color=color, label=LABELS[key].replace("\n", " "),
        )
    axes[2, 1].set_xlabel("Mean reader latency (seconds/question)")
    axes[2, 1].set_ylabel("Official GPT-4o judge accuracy (%)")
    axes[2, 1].set_title("Absolute accuracy versus reader latency")
    axes[2, 1].legend(fontsize=7, loc="center left", bbox_to_anchor=(1.01, .5))

    for axis in axes.flat:
        axis.grid(alpha=.18)
        axis.set_axisbelow(True)
    figure.patch.set_facecolor("#090b10")
    png.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(png, dpi=190, facecolor=figure.get_facecolor())
    figure.savefig(svg, facecolor=figure.get_facecolor())
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()
    render(json.loads(args.input.read_text(encoding="utf-8")), args.png, args.svg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
