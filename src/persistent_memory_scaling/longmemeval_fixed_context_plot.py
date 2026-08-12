"""Plot the completed LongMemEval-S 2K/28K fixed-context endpoint matrix."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/pmsb-matplotlib")

SYSTEMS = (
    "asm_bridge81",
    "vector_bridge81",
    "bm25_bridge81",
    "vector_bm25_rrf_bridge81",
    "trustgraph_graph_embeddings",
)
BUDGETS = (2_000, 28_000)
LABELS = {
    "asm_bridge81": "ASM-CM + Bridge 8.1",
    "vector_bridge81": "Vector + Bridge 8.1",
    "bm25_bridge81": "BM25 + Bridge 8.1",
    "vector_bm25_rrf_bridge81": "Vector + BM25 RRF\n+Bridge 8.1",
    "trustgraph_graph_embeddings": "TrustGraph\ngraph-embeddings",
}
COLORS = {
    "asm_bridge81": "#55d6be",
    "vector_bridge81": "#7aa2f7",
    "bm25_bridge81": "#f6c85f",
    "vector_bm25_rrf_bridge81": "#bb9af7",
    "trustgraph_graph_embeddings": "#ff7a90",
}


def measurements(payload: dict[str, Any]) -> dict[tuple[str, int], dict[str, float]]:
    if not payload.get("complete"):
        raise ValueError("fixed-context run is not complete")
    summary = payload["summary"]
    official = payload["official_evaluation"]["results"]
    rows = payload["rows"]
    result: dict[tuple[str, int], dict[str, float]] = {}
    for system in SYSTEMS:
        for budget in BUDGETS:
            key = f"{system}_b{budget}"
            selected = [
                row for row in rows
                if row["system"] == system and int(row["evidence_token_budget"]) == budget
            ]
            failures = sum(bool(row.get("reader_contract_failure")) for row in selected)
            result[(system, budget)] = {
                "examples": float(official[key]["examples"]),
                "accuracy": float(official[key]["accuracy"]) * 100,
                "correct": float(official[key]["correct"]),
                "input_tokens_mean": float(summary[key]["reader_input_tokens_mean"]),
                "input_tokens_total": float(summary[key]["reader_input_tokens_total"]),
                "reader_latency_ms_mean": float(summary[key]["reader_latency_ms_mean"]),
                "retrieval_recall": float(summary[key]["retrieval_recall"]) * 100,
                "contract_failures": float(failures),
            }
    return result


def _finish(figure: Any, png: Path, svg: Path) -> None:
    png.parent.mkdir(parents=True, exist_ok=True)
    figure.patch.set_facecolor("#090b10")
    figure.savefig(png, dpi=190, facecolor=figure.get_facecolor(), bbox_inches="tight")
    figure.savefig(svg, facecolor=figure.get_facecolor(), bbox_inches="tight")


def render_dashboard(data: dict[tuple[str, int], dict[str, float]], png: Path, svg: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    plt.style.use("dark_background")
    figure, axes = plt.subplots(2, 2, figsize=(18, 12), constrained_layout=True)
    figure.suptitle(
        "LongMemEval-S fixed-context endpoints — 500 questions, GPT-4o reader and judge\n"
        "Frozen gold-blind rankings; measured 2K and 28K evidence-token budgets",
        fontsize=17, weight="bold",
    )
    x = np.arange(len(SYSTEMS))
    width = .36
    labels = [LABELS[system] for system in SYSTEMS]

    for offset, budget, hatch in ((-.5, 2_000, ""), (.5, 28_000, "//")):
        values = [data[(system, budget)]["accuracy"] for system in SYSTEMS]
        bars = axes[0, 0].bar(
            x + offset * width, values, width,
            color=[COLORS[system] for system in SYSTEMS], alpha=.95 if budget == 2_000 else .7,
            hatch=hatch, edgecolor="#ddd", linewidth=.35,
            label=f"{budget // 1000}K budget",
        )
        axes[0, 0].bar_label(bars, labels=[f"{value:.1f}%" for value in values], padding=3, fontsize=8)
    axes[0, 0].set_title("Official answer accuracy")
    axes[0, 0].set_ylabel("Official GPT-4o judge accuracy (%)")
    axes[0, 0].set_xticks(x, labels)
    axes[0, 0].legend(ncols=2)

    for system in SYSTEMS:
        tokens = [data[(system, budget)]["input_tokens_mean"] for budget in BUDGETS]
        accuracy = [data[(system, budget)]["accuracy"] for budget in BUDGETS]
        axes[0, 1].plot(
            tokens, accuracy, marker="o", linewidth=2.2, markersize=7,
            color=COLORS[system], label=LABELS[system].replace("\n", " "),
        )
        axes[0, 1].annotate(
            f"{accuracy[-1]:.1f}%", (tokens[-1], accuracy[-1]),
            xytext=(5, 4), textcoords="offset points", fontsize=8,
        )
    axes[0, 1].set_xscale("log")
    axes[0, 1].set_title("Accuracy bought with reader context")
    axes[0, 1].set_xlabel("Measured mean reader input tokens/question (log scale)")
    axes[0, 1].set_ylabel("Official accuracy (%)")
    axes[0, 1].legend(fontsize=8, loc="best")

    for offset, budget, hatch in ((-.5, 2_000, ""), (.5, 28_000, "//")):
        values = [data[(system, budget)]["reader_latency_ms_mean"] / 1000 for system in SYSTEMS]
        bars = axes[1, 0].bar(
            x + offset * width, values, width,
            color=[COLORS[system] for system in SYSTEMS], alpha=.95 if budget == 2_000 else .7,
            hatch=hatch, edgecolor="#ddd", linewidth=.35,
            label=f"{budget // 1000}K budget",
        )
        axes[1, 0].bar_label(bars, labels=[f"{value:.2f}s" for value in values], padding=3, fontsize=8)
    axes[1, 0].set_title("Reader-only latency — retrieval runtime excluded")
    axes[1, 0].set_ylabel("Mean reader latency (seconds/question)")
    axes[1, 0].set_xticks(x, labels)
    axes[1, 0].legend(ncols=2)

    recall = [data[(system, 2_000)]["retrieval_recall"] for system in SYSTEMS]
    accuracy_2k = [data[(system, 2_000)]["accuracy"] for system in SYSTEMS]
    scatter_offsets = {
        "asm_bridge81": (5, 5),
        "vector_bridge81": (-15, -16),
        "bm25_bridge81": (-3, 10),
        "vector_bm25_rrf_bridge81": (6, 13),
        "trustgraph_graph_embeddings": (5, -13),
    }
    for system, rx, ay in zip(SYSTEMS, recall, accuracy_2k, strict=True):
        axes[1, 1].scatter(rx, ay, s=110, color=COLORS[system], label=LABELS[system].replace("\n", " "))
        axes[1, 1].annotate(
            LABELS[system], (rx, ay), xytext=scatter_offsets[system],
            textcoords="offset points", fontsize=8,
            ha="right" if scatter_offsets[system][0] < 0 else "left",
        )
    axes[1, 1].set_title("Frozen retrieval recall vs. 2K answer accuracy")
    axes[1, 1].set_xlabel("Retrieval Recall@15 (%)")
    axes[1, 1].set_ylabel("Official accuracy at 2K (%)")

    for axis in axes.flat:
        axis.grid(alpha=.18)
        axis.set_axisbelow(True)
    failure_total = int(sum(item["contract_failures"] for item in data.values()))
    figure.text(
        .5, -.012,
        f"Measured only. n=500 per cell. {failure_total} fail-closed reader contract failures at 2K "
        "were scored incorrect; 0 at 28K. Rankings were reused, so latency is reader-only.",
        ha="center", fontsize=9, color="#c8ccd4",
    )
    _finish(figure, png, svg)
    plt.close(figure)


def render_delta(data: dict[tuple[str, int], dict[str, float]], png: Path, svg: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.style.use("dark_background")
    figure, axes = plt.subplots(1, 2, figsize=(16, 7), constrained_layout=True)
    figure.suptitle(
        "What did 14× more evidence budget buy? — LongMemEval-S, n=500 per system",
        fontsize=16, weight="bold",
    )
    delta_tokens = []
    delta_accuracy = []
    for system in SYSTEMS:
        small = data[(system, 2_000)]
        large = data[(system, 28_000)]
        dt = large["input_tokens_mean"] - small["input_tokens_mean"]
        da = large["accuracy"] - small["accuracy"]
        delta_tokens.append(dt)
        delta_accuracy.append(da)
        axes[0].scatter(dt, da, s=125, color=COLORS[system])
        axes[0].annotate(LABELS[system], (dt, da), xytext=(5, 5), textcoords="offset points", fontsize=8)
    axes[0].axhline(0, color="#aaa", linewidth=.8)
    axes[0].set_title("Marginal context versus accuracy change")
    axes[0].set_xlabel("Additional mean reader input tokens/question")
    axes[0].set_ylabel("Accuracy change, 2K → 28K (percentage points)")

    values = []
    for system, dt, da in zip(SYSTEMS, delta_tokens, delta_accuracy, strict=True):
        values.append(da / (dt / 1000))
    bars = axes[1].barh(range(len(SYSTEMS)), values, color=[COLORS[s] for s in SYSTEMS])
    axes[1].set_yticks(range(len(SYSTEMS)), [LABELS[s] for s in SYSTEMS])
    axes[1].invert_yaxis()
    axes[1].axvline(0, color="#aaa", linewidth=.8)
    axes[1].set_title("Marginal context efficiency")
    axes[1].set_xlabel("Accuracy points gained per additional 1K input tokens")
    axes[1].bar_label(bars, labels=[f"{value:+.2f}" for value in values], padding=3, fontsize=9)
    for axis in axes:
        axis.grid(alpha=.18)
        axis.set_axisbelow(True)
    figure.text(
        .5, -.01,
        "Negative values mean that the larger evidence package reduced official answer accuracy in this measured run.",
        ha="center", fontsize=9, color="#c8ccd4",
    )
    _finish(figure, png, svg)
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    data = measurements(json.loads(args.input.read_text(encoding="utf-8")))
    render_dashboard(
        data,
        args.output_dir / "longmemeval-fixed-context-2k-28k.png",
        args.output_dir / "longmemeval-fixed-context-2k-28k.svg",
    )
    render_delta(
        data,
        args.output_dir / "longmemeval-fixed-context-delta.png",
        args.output_dir / "longmemeval-fixed-context-delta.svg",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
