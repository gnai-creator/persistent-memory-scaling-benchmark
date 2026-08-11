"""Render protocol-separated charts from completed ASM benchmark artifacts."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/pmsb-matplotlib")

COLORS = ["#55d6be", "#2dd4bf", "#f6c85f", "#7aa2f7", "#bb9af7", "#ff7a90"]


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


def render_longmemeval(data: dict[str, Any], output: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.style.use("dark_background")
    summary = data["summary"]
    official = data["official_evaluation"]["results"]["asm_bridge81_gpt4o"]
    figure, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    figure.suptitle(
        "ASM-CM + Bridge 8.1 on LongMemEval-S — complete 500/500 with GPT-4o\n"
        "External generalization result; diagnostic score and official judge are different metrics",
        fontsize=15, weight="bold",
    )
    _bars(
        axes[0, 0], ["Retrieval\nRecall@15", "Diagnostic\nanswer score", "Official GPT-4o\njudge accuracy"],
        [summary["retrieval_recall"] * 100, summary["diagnostic_answer_score"] * 100,
         official["accuracy"] * 100], ylabel="Percent", title="Quality metrics — do not conflate",
        suffix="%",
    )
    _bars(
        axes[0, 1], ["Reader input", "Reader output"],
        [summary["reader_input_tokens_total"] / 1e6, summary["reader_output_tokens_total"] / 1e6],
        ylabel="Tokens (millions)", title="Measured GPT-4o token usage", suffix="M", decimals=3,
    )
    latency = [summary["retrieval_latency_ms_mean"] / 1000, summary["reader_latency_ms_mean"] / 1000]
    bars = axes[1, 0].bar(["ASM retrieval", "GPT-4o reader"], latency, color=COLORS[:2])
    axes[1, 0].set_ylabel("Mean latency per question (seconds)")
    axes[1, 0].set_title("Operational latency components")
    axes[1, 0].bar_label(bars, labels=[f"{value:.2f}s" for value in latency], padding=3)
    _bars(
        axes[1, 1], ["Answer\ncontainment", "Exact\nmatch", "Abstention\naccuracy"],
        [summary["answer_containment"] * 100, summary["exact_match"] * 100,
         summary["abstention_accuracy"] * 100], ylabel="Percent",
        title="Additional diagnostics", suffix="%",
    )
    _style(figure, axes)
    _save(figure, output)
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asm-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
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
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
