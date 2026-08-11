"""Plot the separate ASM-CM + Memory Bridge Phase 8.1 operational point."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/pmsb-matplotlib")


def render(data: dict, png: Path, svg: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    plt.style.use("dark_background")
    figure, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    figure.suptitle(
        "ASM-CM + Memory Bridge 8.1 — separate operational point\n"
        "Frozen ASM retrieval replay; not a 100–100k scaling curve",
        fontsize=16, weight="bold",
    )

    resources = data["resources"]
    axis = axes[0, 0]
    labels = ["Peak RSS", "Peak VRAM"]
    bridge = np.array([resources["bridge_rss_peak_bytes"], resources["bridge_vram_peak_bytes"]]) / 1e9
    reader = np.array([resources["reader_rss_peak_bytes"], resources["reader_vram_peak_bytes"]]) / 1e9
    x = np.arange(2)
    axis.bar(x, bridge, label="Bridge process tree", color="#55d6be")
    axis.bar(x, reader, bottom=bridge, label="Qwen3 14B reader (separate)", color="#ffca5c")
    axis.set_xticks(x, labels)
    axis.set_ylabel("Memory (GB)")
    axis.set_title("Continuous 1 s resource sampling")
    axis.legend(fontsize=8)
    for position, total in zip(x, bridge + reader):
        axis.annotate(f"{total:.2f} GB", (position, total), xytext=(0, 7),
                      textcoords="offset points", ha="center", weight="bold")

    systems = data["systems"]
    order = ["asm_compact", "vector", "bm25"]
    names = ["ASM compact", "Vector RAG", "BM25"]
    colors = ["#55d6be", "#7aa2f7", "#bb9af7"]

    axis = axes[0, 1]
    tokens = [systems[key]["reader_input_tokens_total"] / 1e6 for key in order]
    axis.bar(names, tokens, color=colors)
    axis.set_ylabel("Reader input tokens (millions)")
    axis.set_title("979 questions — measured requests")

    axis = axes[1, 0]
    width = .36
    recall = [systems[key]["retrieval_recall"] * 100 for key in order]
    quality = [systems[key]["diagnostic_answer_score"] * 100 for key in order]
    positions = np.arange(3)
    axis.bar(positions - width / 2, recall, width, label="Retrieval recall", color="#7aa2f7")
    axis.bar(positions + width / 2, quality, width, label="Answer score", color="#55d6be")
    axis.set_xticks(positions, names)
    axis.set_ylabel("Percent")
    axis.set_title("Retrieval and answer quality")
    axis.legend(fontsize=8)

    axis = axes[1, 1]
    latency = [systems[key]["reader_latency_ms_mean"] for key in order]
    axis.bar(names, latency, color=colors)
    axis.set_ylabel("Mean reader latency (ms)")
    axis.set_title("Concurrent-GPU condition — do not compare to isolated runs")

    for axis in axes.flat:
        axis.grid(axis="y", alpha=.2)
    png.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(png, dpi=180)
    figure.savefig(svg)
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()
    render(json.loads(args.input.read_text(encoding="utf-8")), args.png, args.svg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
