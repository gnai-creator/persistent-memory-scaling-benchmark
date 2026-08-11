"""Matplotlib comparison of TrustGraph stack RAM and attributed VRAM."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

# Matplotlib otherwise tries to create a cache below the user's home directory.
os.environ.setdefault("MPLCONFIGDIR", "/tmp/pmsb-matplotlib")


def render(data: dict, png: Path, svg: Path, asm_reference: dict | None = None) -> None:
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
    if asm_reference is not None:
        bridge_ram = asm_reference["resources"]["bridge_rss_peak_bytes"] / 1e9
        bridge_vram = asm_reference["resources"]["bridge_vram_peak_bytes"] / 1e9
        axis.scatter([2], [bridge_ram], marker="D", s=90, color="#7aa2f7", zorder=6,
                     label="ASM-CM + Bridge 8.1 peak RSS reference")
        axis.annotate(
            f"ASM-CM + Bridge 8.1\n{bridge_ram:.3f} GB peak RSS; "
            f"{bridge_vram:.0f} B attributed VRAM",
            (2, bridge_ram), xytext=(0, 25), textcoords="offset points",
            ha="center", color="#7aa2f7", weight="bold",
        )
        axis.set_xticks([0, 1, 2], labels + ["ASM operational"])
    else:
        axis.set_xticks(x, labels)
    axis.set_ylabel("Memory (GB; statistic labeled)")
    axis.set_ylim(0, max(ram) * 1.18)
    axis.set_title("TrustGraph stack vs. ASM-CM operational memory", fontsize=18, weight="bold")
    axis.text(.5, -.14, "TrustGraph bars: 30 s mean. ASM diamond: separate Phase 8.1 peak RSS; reader excluded.",
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
    parser.add_argument("--asm-reference")
    args = parser.parse_args()
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    asm_reference = (json.loads(Path(args.asm_reference).read_text(encoding="utf-8"))
                     if args.asm_reference else None)
    render(data, Path(args.png), Path(args.svg), asm_reference)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
