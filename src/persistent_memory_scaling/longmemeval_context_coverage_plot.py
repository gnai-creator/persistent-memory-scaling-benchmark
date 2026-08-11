"""Render TrustGraph LongMemEval history-to-reader coverage diagnostics."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/pmsb-matplotlib")


def render(payload: dict, png: Path, svg: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = payload["rows"]
    summary = payload["summary"]
    plt.style.use("dark_background")
    figure, axes = plt.subplots(2, 2, figsize=(16, 10), constrained_layout=True)
    figure.suptitle(
        "TrustGraph graph-embeddings — how much LongMemEval history reached GPT-4o?\n"
        "Completed 500-question uncompacted ablation",
        fontsize=16, weight="bold",
    )

    token_values = [
        summary["available_history_tokens_o200k"]["mean"],
        summary["selected_content_tokens_o200k"]["mean"],
        summary["provider_reader_input_tokens"]["mean"],
    ]
    bars = axes[0, 0].bar(
        ["Available history\ncontent", "Selected evidence\ncontent", "Complete reader\ninput"],
        token_values, color=["#7aa2f7", "#f7768e", "#f6c85f"],
    )
    axes[0, 0].bar_label(bars, labels=[f"{value/1000:.1f}k" for value in token_values], padding=4)
    axes[0, 0].set_ylabel("Mean tokens per question")
    axes[0, 0].set_title("Context volume")

    fractions = [100 * row["selected_token_fraction"] for row in rows]
    axes[0, 1].hist(fractions, bins=20, color="#f7768e", edgecolor="#090b10")
    axes[0, 1].axvline(sum(fractions) / len(fractions), color="#f6c85f", linestyle="--",
                       label=f"Mean: {sum(fractions)/len(fractions):.0f}%")
    axes[0, 1].set_xlabel("Selected evidence / available history tokens (%)")
    axes[0, 1].set_ylabel("Questions")
    axes[0, 1].set_title("History fraction selected")
    axes[0, 1].legend()

    available = [row["available_history_tokens_o200k"] / 1000 for row in rows]
    selected = [row["selected_content_tokens_o200k"] / 1000 for row in rows]
    axes[1, 0].scatter(available, selected, s=18, alpha=.55, color="#55d6be")
    axes[1, 0].set_xlabel("Available history tokens (thousands)")
    axes[1, 0].set_ylabel("Selected evidence tokens (thousands)")
    axes[1, 0].set_title("Per-question selection")

    memory_values = [summary["available_memories"]["mean"], summary["included_memories"]["mean"]]
    bars = axes[1, 1].bar(
        ["Available history\nmemories", "Included evidence\nmemories"], memory_values,
        color=["#7aa2f7", "#f7768e"],
    )
    axes[1, 1].bar_label(bars, labels=[f"{value:.1f}" for value in memory_values], padding=4)
    axes[1, 1].set_ylabel("Mean memories per question")
    axes[1, 1].set_title("Memory-count coverage")

    for axis in axes.flat:
        axis.grid(alpha=.18)
        axis.set_axisbelow(True)
    figure.text(
        .5, .005,
        "Measured result: TrustGraph selected ~26% of history tokens on average — not the full history. "
        "Retrieval value versus matched full-history/random controls remains under evaluation.",
        ha="center", fontsize=10,
    )
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
