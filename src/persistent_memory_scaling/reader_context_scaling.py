"""Aggregate and plot reader-context distributions as history grows."""

from __future__ import annotations

import argparse
import json
import math
import os
from collections import defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable

os.environ.setdefault("MPLCONFIGDIR", "/tmp/pmsb-matplotlib")

REQUIRED = ("system", "history_events", "reader_context_tokens", "recall_at_5", "qa_score")


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def validate_row(row: dict[str, Any], index: int) -> None:
    missing = [key for key in REQUIRED if key not in row]
    if missing:
        raise ValueError(f"row {index} is missing: {', '.join(missing)}")
    if not str(row["system"]).strip() or int(row["history_events"]) <= 0:
        raise ValueError(f"row {index} has an invalid system or history_events")
    if float(row["reader_context_tokens"]) < 0:
        raise ValueError(f"row {index} has negative reader_context_tokens")
    for key in ("recall_at_5", "qa_score"):
        value = float(row[key])
        if not 0 <= value <= 1:
            raise ValueError(f"row {index} has {key} outside [0, 1]")


def aggregate(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    row_list = list(rows)
    for index, row in enumerate(row_list):
        validate_row(row, index)
        groups[(str(row["system"]), int(row["history_events"]))].append(row)
    if not groups:
        raise ValueError("input contains no observations")

    points = []
    for (system, history_events), selected in sorted(groups.items(), key=lambda item: (item[0][1], item[0][0])):
        tokens = [float(row["reader_context_tokens"]) for row in selected]
        point = {
            "system": system,
            "history_events": history_events,
            "n": len(selected),
            "context_tokens": {
                "p50": percentile(tokens, .50),
                "p95": percentile(tokens, .95),
                "p99": percentile(tokens, .99),
                "mean": fmean(tokens),
            },
            "recall_at_5": fmean(float(row["recall_at_5"]) for row in selected),
            "qa_score": fmean(float(row["qa_score"]) for row in selected),
        }
        if all("reader_contract_failure" in row for row in selected):
            point["reader_contract_failure_rate"] = fmean(
                float(bool(row["reader_contract_failure"])) for row in selected
            )
        points.append(point)
    return {
        "schema_version": "reader-context-scaling-summary-v1",
        "measurement_status": "measured",
        "points": points,
        "interpretation_gate": (
            "Compare context curves only at matched retrieval/answer quality; "
            "a lower token percentile alone is not an efficiency win."
        ),
    }


def render(summary: dict[str, Any], png: Path, svg: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    points = summary["points"]
    recall_label = str(summary.get("recall_label", "Recall@5"))
    systems = sorted({point["system"] for point in points})
    if not points:
        raise ValueError("summary contains no points")
    measurement_status = summary.get("measurement_status")
    illustrative = measurement_status not in {"measured", "measured-integration-smoke"}

    plt.style.use("dark_background")
    figure, axes = plt.subplots(1, 2, figsize=(15, 6.5), constrained_layout=True)
    if measurement_status == "measured-integration-smoke":
        title_suffix = "MEASURED INTEGRATION SMOKE — NOT A SCALING RESULT"
    else:
        title_suffix = "PROTOCOL ILLUSTRATION — NOT MEASURED" if illustrative else "MEASURED"
    subject = systems[0] if len(systems) == 1 else "ASM Memory Bridge vs RAG"
    figure.suptitle(f"{subject} — context scaling conditioned on quality\n{title_suffix}", fontsize=17, weight="bold")
    colors = ("#55d6be", "#7aa2f7", "#ffca5c", "#bb9af7", "#f7768e")

    for system, color in zip(systems, colors, strict=False):
        display = "ASM" if system == "ASM Memory Bridge" else (
            "RAG" if system.startswith("RAG (") else system
        )
        selected = sorted((p for p in points if p["system"] == system), key=lambda p: p["history_events"])
        x = [p["history_events"] for p in selected]
        for quantile, style, alpha in (("p50", "-", 1), ("p95", "--", .9), ("p99", ":", .8)):
            axes[0].plot(x, [p["context_tokens"][quantile] for p in selected], marker="o",
                         linestyle=style, color=color, alpha=alpha, linewidth=2,
                         label=f"{display} {quantile}")
        axes[1].plot(x, [100 * p["recall_at_5"] for p in selected], "o-", color=color,
                     linewidth=2.2, label=f"{display} {recall_label}")
        axes[1].plot(x, [100 * p["qa_score"] for p in selected], "s--", color=color,
                     linewidth=1.8, alpha=.85, label=f"{display} QA")
        if all("reader_contract_failure_rate" in p for p in selected):
            axes[1].plot(
                x, [100 * p["reader_contract_failure_rate"] for p in selected], "^:",
                color=color, linewidth=1.5, alpha=.75, label=f"{display} contract failure",
            )

    axes[0].set_title("History size → context delivered to the reader")
    axes[0].set_ylabel("Reader-context tokens per query")
    axes[1].set_title("History size → retrieval and answer quality")
    axes[1].set_ylabel("Quality (%)")
    axes[1].set_ylim(0, 105)
    for axis in axes:
        axis.set_xscale("log")
        axis.set_xlabel("Historical events (log scale)")
        axis.grid(alpha=.2)
        axis.legend(fontsize=7, ncol=2)
    png.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(png, dpi=180)
    figure.savefig(svg)
    plt.close(figure)


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("JSON input must be an array of observations")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="JSON array or JSONL observations")
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()
    result = aggregate(_read_rows(args.input))
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    render(result, args.png, args.svg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
