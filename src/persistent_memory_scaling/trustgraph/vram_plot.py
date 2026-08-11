"""Matplotlib comparison of TrustGraph stack RAM and attributed VRAM."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

# Matplotlib otherwise tries to create a cache below the user's home directory.
os.environ.setdefault("MPLCONFIGDIR", "/tmp/pmsb-matplotlib")


def render(data: dict, png: Path, svg: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    plt.style.use("dark_background")
    labels = ["Stack off", "c100k stack idle"]
    states = [data["stack_down"], data["stack_up_c100k_idle"]]
    ram = np.array([state["container_ram_mean_bytes"] / 1e9 for state in states])
    vram = np.array([state["trustgraph_mean_bytes"] / 1e9 for state in states])
    x = np.arange(2)
    figure, axis = plt.subplots(figsize=(11, 7), constrained_layout=True)
    width = .32
    ram_bars = axis.bar(x - width / 2, ram, width, label="TrustGraph container RAM", color="#55d6be")
    vram_bars = axis.bar(x + width / 2, vram, width, label="TrustGraph-attributed VRAM", color="#ffca5c")
    for bar, value in zip(ram_bars, ram):
        label = f"{value:.2f} GB" if value else "0 B"
        axis.annotate(label, (bar.get_x() + bar.get_width() / 2, value), xytext=(0, 7),
                      textcoords="offset points", ha="center", weight="bold")
    for bar, value in zip(vram_bars, vram):
        label = f"{value:.2f} GB" if value else "0 B"
        axis.annotate(label, (bar.get_x() + bar.get_width() / 2, value), xytext=(0, 7),
                      textcoords="offset points", ha="center", color="#ffca5c", weight="bold")
    axis.set_xticks(x, labels)
    axis.set_ylabel("Mean memory (GB)")
    axis.set_ylim(0, max(ram) * 1.18)
    axis.set_title("TrustGraph stack memory footprint — TG-2 (30 s idle mean)", fontsize=18, weight="bold")
    axis.text(.5, -.14, "30 s mean, not peak. Only TrustGraph resources are shown; system and ASM are excluded.",
              transform=axis.transAxes, ha="center", color="#a9b1d6")
    axis.grid(axis="y", alpha=.2)
    axis.legend(ncol=2, fontsize=10)
    png.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(png, dpi=180)
    figure.savefig(svg)
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--png", required=True)
    parser.add_argument("--svg", required=True)
    args = parser.parse_args()
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    render(data, Path(args.png), Path(args.svg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
