"""Render protocol-separated charts from completed ASM benchmark artifacts."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/pmsb-matplotlib")

COLORS = ["#55d6be", "#2dd4bf", "#f6c85f", "#7aa2f7", "#bb9af7", "#ff7a90", "#ff9e64", "#f7768e"]


def _save(figure: Any, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output.with_suffix(".png"), dpi=190, facecolor=figure.get_facecolor())
    figure.savefig(output.with_suffix(".svg"), facecolor=figure.get_facecolor())


def _bars(axis: Any, labels: list[str], values: list[float], *, ylabel: str,
          title: str, suffix: str = "", decimals: int = 1) -> None:
    bars = axis.bar(range(len(labels)), values, color=COLORS[:len(labels)])
    axis.set_xticks(range(len(labels)), labels)
    axis.set_ylabel(ylabel)
    axis.set_title(title)
    axis.bar_label(
        bars, labels=[f"{value:.{decimals}f}{suffix}" for value in values],
        padding=3, fontsize=8,
    )


def _style(figure: Any, axes: Any) -> None:
    for axis in axes.flat:
        axis.grid(axis="y", alpha=.18)
        axis.set_axisbelow(True)
        axis.tick_params(axis="x", labelsize=8)
    figure.patch.set_facecolor("#090b10")


def render_multiwoz(baseline: dict[str, Any], hybrid: dict[str, Any], output: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.style.use("dark_background")
    systems = dict(baseline["summary"])
    systems.update(hybrid["summary"])
    order = ["asm", "asm_compact", "asm_vector_bm25_compact", "vector", "bm25"]
    labels = ["ASM-CM\nraw context", "ASM-CM +\nBridge 8.1", "ASM + Vector +\nBM25 compact", "Vector RAG", "BM25"]
    figure, axes = plt.subplots(2, 2, figsize=(16, 9), constrained_layout=True)
    figure.suptitle(
        "Completed ASM MultiWOZ Phase 8.1 results — same 979 questions and Qwen3 14B reader\n"
        "The hybrid saves more context but does not improve retrieval or answer quality",
        fontsize=15, weight="bold",
    )
    _bars(axes[0, 0], labels, [systems[k]["retrieval_recall"] * 100 for k in order],
          ylabel="Recall@5 (%)", title="Retrieval quality", suffix="%")
    _bars(axes[0, 1], labels, [systems[k]["diagnostic_answer_score"] * 100 for k in order],
          ylabel="Diagnostic score (%)", title="Answer quality", suffix="%")
    _bars(axes[1, 0], labels, [systems[k]["reader_input_tokens_total"] / 1e6 for k in order],
          ylabel="Reader input tokens (millions)", title="Measured context sent to the reader",
          suffix="M", decimals=2)
    _bars(axes[1, 1], labels, [systems[k]["exact_match"] * 100 for k in order],
          ylabel="Exact match (%)", title="Strict answer match", suffix="%")
    _style(figure, axes)
    _save(figure, output)
    plt.close(figure)


def render_free128(data: dict[str, Any], output: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.style.use("dark_background")
    systems = data["summary"]
    order = ["vector_reader", "vector_compact", "vector_context_residual_compact",
             "bm25_compact", "asm_bindings_compact"]
    labels = [
        "Vector RAG\ncontrol\n(no ASM-CM)",
        "Vector RAG +\nBridge compact\n(no ASM-CM)",
        "Vector + ASM-CM\nresidual + Bridge",
        "BM25 +\nBridge compact\n(no ASM-CM)",
        "ASM-CM bindings\n+ Bridge compact",
    ]
    figure, axes = plt.subplots(2, 2, figsize=(16, 9), constrained_layout=True)
    figure.suptitle(
        "ASM-CM R3.2 free-language evaluation — 128 questions\n"
        "Completed but not promoted: the residual head failed recall preservation",
        fontsize=15, weight="bold",
    )
    _bars(axes[0, 0], labels, [systems[k]["retrieval_recall"] * 100 for k in order],
          ylabel="Recall@5 (%)", title="Retrieval quality", suffix="%")
    _bars(axes[0, 1], labels, [systems[k]["diagnostic_answer_score"] * 100 for k in order],
          ylabel="Diagnostic score (%)", title="Answer quality", suffix="%")
    _bars(axes[1, 0], labels, [systems[k]["reader_input_tokens_total"] / 1000 for k in order],
          ylabel="Reader input tokens (thousands)", title="Measured context volume",
          suffix="k", decimals=0)
    _bars(axes[1, 1], labels, [systems[k]["reader_latency_ms_mean"] / 1000 for k in order],
          ylabel="Mean reader latency (seconds)", title="Observed runtime — shared contention",
          suffix="s")
    _style(figure, axes)
    _save(figure, output)
    plt.close(figure)


def render_longmemeval(
    data: dict[str, Any], output: Path, hybrids: dict[str, Any] | None = None,
    trustgraph: dict[str, Any] | None = None,
) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.style.use("dark_background")
    if hybrids is None:
        summary = {"asm_bridge81_gpt4o": data["summary"]}
        official = data["official_evaluation"]["results"]
    else:
        summary = hybrids["summary"]
        official = hybrids["official_evaluation"]["results"]
    if trustgraph is not None:
        summary = dict(summary)
        official = dict(official)
        summary["trustgraph_graph_embeddings_gpt4o"] = trustgraph["summary"]
        official["trustgraph_graph_embeddings_gpt4o"] = (
            trustgraph["official_evaluation"]["results"][
                "trustgraph_graph_embeddings_gpt4o"
            ]
        )
    order = [
        "asm_bridge81_gpt4o", "vector_bridge81_gpt4o", "bm25_bridge81_gpt4o",
        "asm_vector_rrf_bridge81_gpt4o", "asm_bm25_rrf_bridge81_gpt4o",
        "vector_bm25_rrf_bridge81_gpt4o", "asm_vector_bm25_rrf_bridge81_gpt4o",
        "trustgraph_graph_embeddings_gpt4o",
    ]
    order = [key for key in order if key in summary]
    labels = {
        "asm_bridge81_gpt4o": "ASM-CM + Bridge",
        "vector_bridge81_gpt4o": "Vector + Bridge",
        "bm25_bridge81_gpt4o": "BM25 + Bridge",
        "asm_vector_rrf_bridge81_gpt4o": "ASM + Vector RRF",
        "asm_bm25_rrf_bridge81_gpt4o": "ASM + BM25 RRF",
        "vector_bm25_rrf_bridge81_gpt4o": "Vector + BM25 RRF",
        "asm_vector_bm25_rrf_bridge81_gpt4o": "ASM + Vector + BM25 RRF",
        "trustgraph_graph_embeddings_gpt4o": "TrustGraph graph-embeddings\n(uncompacted)",
    }
    figure, axes = plt.subplots(2, 2, figsize=(17, 11), constrained_layout=True)
    figure.suptitle(
        "LongMemEval-S paired comparison — complete 500/500 with GPT-4o\n"
        "TrustGraph uses graph-embeddings retrieval and is uncompacted, not Full GraphRAG",
        fontsize=15, weight="bold",
    )
    panels = [
        (axes[0, 0], "Recall@15 (%)", "Retrieval quality",
         [summary[key]["retrieval_recall"] * 100 for key in order], "%", 1),
        (axes[0, 1], "Official accuracy (%)", "Official GPT-4o judge",
         [official[key]["accuracy"] * 100 for key in order], "%", 1),
        (axes[1, 0], "Input tokens per question", "Measured reader context",
         [summary[key]["reader_input_tokens_mean"] for key in order], "", 0),
        (axes[1, 1], "Reader latency (seconds/question)",
         "GPT-4o reader latency — retrieval precompute excluded",
         [summary[key]["reader_latency_ms_mean"] / 1000 for key in order], "s", 2),
    ]
    for axis, xlabel, title, values, suffix, decimals in panels:
        bars = axis.barh(range(len(order)), values, color=COLORS[:len(order)])
        axis.set_yticks(range(len(order)), [labels[key] for key in order])
        axis.invert_yaxis()
        axis.set_xlabel(xlabel)
        axis.set_title(title)
        axis.bar_label(
            bars, labels=[f"{value:.{decimals}f}{suffix}" for value in values],
            padding=3, fontsize=8,
        )
    _style(figure, axes)
    _save(figure, output)
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asm-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--trustgraph-longmemeval", type=Path)
    args = parser.parse_args()
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    runs = args.asm_root / "runs"
    render_multiwoz(
        load(runs / "asm_memory_bridge_phase81/results.json"),
        load(runs / "asm_memory_bridge_phase81_hybrid/results.json"),
        args.output_dir / "asm-multiwoz-phase81-complete",
    )
    render_free128(
        load(runs / "dual_asm_r32/results.json"),
        args.output_dir / "asm-free-language-r32-complete",
    )
    render_longmemeval(
        load(runs / "asm_bridge81_longmemeval_gpt4o/results.json"),
        args.output_dir / "asm-longmemeval-s-500-complete",
        load(runs / "asm_bridge81_longmemeval_hybrids/results.json"),
        load(args.trustgraph_longmemeval) if args.trustgraph_longmemeval else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
