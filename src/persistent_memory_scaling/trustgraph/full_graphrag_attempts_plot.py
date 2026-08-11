"""Plot per-question Full GraphRAG and explainability attempt counts."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/pmsb-matplotlib")


def attempt_series(payload: dict[str, Any]) -> tuple[list[int], list[int | None], list[int | None]]:
    rows = list(payload.get("rows", []))
    questions = list(range(1, len(rows) + 1))
    graph = [
        int(row["full_graphrag_attempts"])
        if row.get("full_graphrag_attempts") is not None else None
        for row in rows
    ]
    explain = [
        int(row["explain_attempts"])
        if row.get("explain_attempts") is not None else None
        for row in rows
    ]
    return questions, graph, explain


def render(payload: dict[str, Any], png: Path, svg: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.ticker import MaxNLocator

    questions, graph, explain = attempt_series(payload)
    x = np.asarray(questions, dtype=float)
    graph_values = np.asarray([np.nan if value is None else value for value in graph])
    explain_values = np.asarray([np.nan if value is None else value for value in explain])
    recorded_graph = int(np.count_nonzero(~np.isnan(graph_values)))
    recorded_explain = int(np.count_nonzero(~np.isnan(explain_values)))

    plt.style.use("dark_background")
    figure, axis = plt.subplots(figsize=(15, 6), constrained_layout=True)
    axis.step(x, graph_values, where="mid", color="#ff7a90", linewidth=1.7,
              label=f"Full GraphRAG ({recorded_graph} recorded)")
    axis.scatter(x, graph_values, color="#ff7a90", s=15, alpha=.8)
    axis.step(x, explain_values, where="mid", color="#7aa2f7", linewidth=1.4,
              label=f"Explainability replay ({recorded_explain} recorded)")
    axis.scatter(x, explain_values, color="#7aa2f7", s=13, alpha=.75)
    axis.axhline(1, color="#55d6be", linestyle="--", linewidth=1.2,
                 label="Success on first attempt")
    axis.set_title("TrustGraph Full GraphRAG — attempts per question", weight="bold")
    axis.set_xlabel("Question sequence in the frozen Phase 8.1 protocol")
    axis.set_ylabel("Attempts")
    axis.set_xlim(.5, max(1.5, len(questions) + .5))
    observed = [value for value in graph + explain if value is not None]
    axis.set_ylim(.75, max(2.25, (max(observed) + .5) if observed else 2.25))
    axis.yaxis.set_major_locator(MaxNLocator(integer=True))
    axis.grid(alpha=.2)
    axis.set_axisbelow(True)
    axis.legend(loc="upper right")
    if recorded_graph + recorded_explain == 0:
        axis.text(
            .5, .5,
            "Attempt counts were not recorded in the legacy smoke rows.\n"
            "The chart will populate as the resumable 979-question run checkpoints.",
            transform=axis.transAxes, ha="center", va="center", color="#d6d7db",
        )
    elif recorded_graph < len(questions) or recorded_explain < len(questions):
        axis.text(
            .01, .02, "Missing legacy values are shown as gaps, not assumed to equal one.",
            transform=axis.transAxes, ha="left", va="bottom", fontsize=9,
            color="#b7b7b7",
        )

    png.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(png, dpi=180)
    figure.savefig(svg)
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
