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
                 png: Path, svg: Path, asm_reference: dict[str, Any] | None = None) -> None:
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

    ram_axis = axes[0, 1]
    ram_points = [item for item in points if "stack_ram_peak_bytes" in item]
    repeated = [item for item in ram_points if item.get("repetitions", 1) > 1]
    single = [item for item in ram_points if item.get("repetitions", 1) == 1]
    if repeated:
        ram_events = [item["events"] for item in repeated]
        ram_values = [item["stack_ram_peak_bytes"] / 1e9 for item in repeated]
        errors = [[(item["stack_ram_peak_bytes"] - item["stack_ram_ci95_low_bytes"]) / 1e9
                   for item in repeated],
                  [(item["stack_ram_ci95_high_bytes"] - item["stack_ram_peak_bytes"]) / 1e9
                   for item in repeated]]
        ram_axis.errorbar(ram_events, ram_values, yerr=errors, fmt="o-", capsize=5,
                          color="#7aa2f7", linewidth=2.5, label="Mean peak ± 95% CI (n=3)")
    if single:
        ram_axis.scatter([item["events"] for item in single],
                         [item["stack_ram_peak_bytes"] / 1e9 for item in single],
                         marker="D", s=70, color="#ffca5c", label="Single run (n=1)", zorder=5)
    for item in ram_points:
        ram_axis.annotate(f'n={item.get("repetitions", 1)}',
                          (item["events"], item["stack_ram_peak_bytes"] / 1e9),
                          xytext=(0, 10), textcoords="offset points", ha="center", fontsize=8)
    if asm_reference is not None:
        asm_peak_gb = asm_reference["resources"]["bridge_rss_peak_bytes"] / 1e9
        ram_axis.axhline(asm_peak_gb, color="#55d6be", linestyle="--", linewidth=2,
                        label="ASM-CM + Bridge 8.1 peak RSS reference")
        ram_axis.annotate(
            f"{asm_peak_gb:.3f} GB — operational reference, not TG-2 scaling",
            (events[-1], asm_peak_gb), xytext=(-4, 8), textcoords="offset points",
            ha="right", color="#55d6be", fontsize=8,
        )
    ram_axis.set_ylabel("Peak container RAM (GB)")
    ram_axis.set_title("TrustGraph stack RAM — measured peak (not 30 s mean)")
    ram_axis.legend(fontsize=8)

    specs = ((axes[1, 0], "query_ms", 1, "Mean latency (ms)", "Structured query — measured only"),
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
    parser.add_argument("--asm-reference")
    args = parser.parse_args()
    points = json.loads(Path(args.points).read_text(encoding="utf-8"))
    projection = extrapolate_storage(points)
    asm_reference = (json.loads(Path(args.asm_reference).read_text(encoding="utf-8"))
                     if args.asm_reference else None)
    render_plots(points, projection, Path(args.png), Path(args.svg), asm_reference)
    write_json(Path(args.output), projection)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
