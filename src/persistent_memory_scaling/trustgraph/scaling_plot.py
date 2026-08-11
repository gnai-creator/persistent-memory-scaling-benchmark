"""Matplotlib plots for measured TG-2 scaling and the 1M projection."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

# Keep headless plot caches outside the repository and the user's home.
os.environ.setdefault("MPLCONFIGDIR", "/tmp/pmsb-matplotlib")
from typing import Any

from .preflight import write_json


def extrapolate_storage(points: list[dict[str, float]], target: int = 1_000_000) -> dict[str, Any]:
    if len(points) < 2 or target <= points[-1]["events"]:
        raise ValueError("need two measured points and a larger target")
    ordered = sorted(points, key=lambda item: item["events"])
    rates = [item["disk_bytes"] / item["events"] for item in ordered[-2:]]
    central_rate = rates[-1]
    return {"target_events": target, "method": "largest-checkpoint bytes/event held constant",
            "central_bytes": central_rate * target,
            "scenario_low_bytes": min(rates) * target,
            "scenario_high_bytes": max(rates) * target,
            "rates_bytes_per_event": rates, "measured_points": ordered,
            "is_measurement": False}


def render_plots(points: list[dict[str, float]], projection: dict[str, Any],
                 png: Path, svg: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.style.use("dark_background")
    figure, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    figure.suptitle("TrustGraph TG-2 — measured scaling and storage projection", fontsize=18, weight="bold")
    events = [item["events"] for item in points]
    disk = [item["disk_bytes"] / 1e9 for item in points]
    axis = axes[0, 0]
    axis.plot(events, disk, "o-", color="#55d6be", linewidth=2.5, label="Measured")
    last = points[-1]
    target = projection["target_events"]
    axis.plot([last["events"], target], [last["disk_bytes"] / 1e9,
              projection["central_bytes"] / 1e9], "o--", color="#ffca5c",
              linewidth=2.5, label="Projected (not measured)")
    axis.annotate(f'≈ {projection["central_bytes"]/1e9:.1f} GB\nPROJECTED',
                  (target, projection["central_bytes"] / 1e9), xytext=(-105, -48),
                  textcoords="offset points", color="#ffca5c", weight="bold",
                  ha="center")
    axis.set_ylabel("Physical storage (GB)")
    axis.set_title("Storage — solid: measured; dotted: projected")
    axis.legend(fontsize=8)

    specs = ((axes[0, 1], "ram_bytes", 1e6, "Paired RAM delta (MB)", "RAM delta — measured only"),
             (axes[1, 0], "query_ms", 1, "Mean latency (ms)", "Structured query — measured only"),
             (axes[1, 1], "events_per_second", 1, "Events/s", "Ingestion throughput — measured only"))
    for current, key, divisor, ylabel, title in specs:
        selected = [(item["events"], item[key] / divisor) for item in points if key in item]
        if selected:
            current.plot([item[0] for item in selected], [item[1] for item in selected],
                         "o-", color="#7aa2f7", linewidth=2.5)
        current.set_ylabel(ylabel)
        current.set_title(title)
    for current in axes.flat:
        current.set_xscale("log")
        current.set_xlabel("Events (log scale)")
        current.grid(alpha=.2)
    png.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(png, dpi=180)
    figure.savefig(svg)
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--points", required=True, help="JSON array with events and disk_bytes")
    parser.add_argument("--svg", required=True)
    parser.add_argument("--png", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    points = json.loads(Path(args.points).read_text(encoding="utf-8"))
    projection = extrapolate_storage(points)
    render_plots(points, projection, Path(args.png), Path(args.svg))
    write_json(Path(args.output), projection)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
