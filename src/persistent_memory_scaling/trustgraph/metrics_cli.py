"""TG-1 metrics command line."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .metrics import (aggregate_deltas, aggregate_official_cycles, delta, sample_window,
                      snapshot, write_snapshot)
from .preflight import write_json
from .client import TrustGraphClient
from .workload import BASE, generate_smoke_workload


def main() -> int:
    parser = argparse.ArgumentParser(prog="pmsb-tg1")
    commands = parser.add_subparsers(dest="command", required=True)
    snap = commands.add_parser("snapshot")
    snap.add_argument("--snapshot-id", required=True)
    snap.add_argument("--phase", required=True, choices=["empty", "post_ingest_idle", "query_peak", "post_query_idle", "cold", "warm"])
    snap.add_argument("--project", default="generated")
    snap.add_argument("--output", required=True)
    snap.add_argument("--exclude-gpu", action="store_true")
    compare = commands.add_parser("delta")
    compare.add_argument("--before", required=True)
    compare.add_argument("--after", required=True)
    compare.add_argument("--events", type=int, required=True)
    compare.add_argument("--output", required=True)
    window = commands.add_parser("window")
    window.add_argument("--window-id", required=True)
    window.add_argument("--phase", required=True)
    window.add_argument("--duration", type=float, required=True)
    window.add_argument("--interval", type=float, default=1.0)
    window.add_argument("--project", default="generated")
    window.add_argument("--output", required=True)
    window.add_argument("--exclude-gpu", action="store_true")
    aggregate = commands.add_parser("aggregate")
    aggregate.add_argument("inputs", nargs="+")
    aggregate.add_argument("--output", required=True)
    official = commands.add_parser("official-aggregate")
    official.add_argument("inputs", nargs="+")
    official.add_argument("--output", required=True)
    workload = commands.add_parser("workload")
    workload.add_argument("--mode", required=True, choices=["ingest", "query"])
    workload.add_argument("--token", required=True)
    workload.add_argument("--flow-id", default="tg1-structured")
    workload.add_argument("--collection", default="tg1-structured")
    workload.add_argument("--queries", type=int, default=100)
    workload.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "snapshot":
        value = snapshot(args.snapshot_id, args.phase, args.project, include_gpu=not args.exclude_gpu)
        write_snapshot(Path(args.output), value)
    elif args.command == "delta":
        before = json.loads(Path(args.before).read_text(encoding="utf-8"))
        after = json.loads(Path(args.after).read_text(encoding="utf-8"))
        value = delta(before, after, args.events)
        write_json(Path(args.output), value)
    elif args.command == "window":
        value = sample_window(args.window_id, args.phase, args.duration, args.interval, args.project,
                              include_gpu=not args.exclude_gpu)
        write_json(Path(args.output), value)
    elif args.command == "aggregate":
        inputs = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.inputs]
        value = aggregate_deltas(inputs)
        write_json(Path(args.output), value)
    elif args.command == "official-aggregate":
        inputs = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.inputs]
        base = Path(args.inputs[0]).parent
        windows = {phase: [json.loads((base / f"{item['run_id']}-{phase}-window.json").read_text(encoding="utf-8"))
                           for item in inputs]
                   for phase in ("empty-control", "loaded", "cold", "warm")}
        value = aggregate_official_cycles(inputs, windows)
        write_json(Path(args.output), value)
    else:
        client = TrustGraphClient("http://localhost:8888/", args.token, flow_id=args.flow_id,
                                  collection=args.collection, timeout=120)
        workload_value = generate_smoke_workload()
        started = time.monotonic()
        if args.mode == "ingest":
            client.start_flow("qwen2.5:0.5b", "sentence-transformers/all-MiniLM-L6-v2")
            # Flow consumers update asynchronously after the lifecycle API returns.
            time.sleep(8)
            count = client.import_events(workload_value["events"])
            client.wait_for_subject(f"{BASE}:person:000", 2, 180)
            client.wait_for_subject(f"{BASE}:person:099", 2, 180)
            value = {"mode": "ingest", "event_count": 100, "triple_count": count,
                     "elapsed_seconds": time.monotonic() - started}
        else:
            latencies = []
            for index in range(args.queries):
                subject = f"{BASE}:person:{index % 100:03d}"
                query_started = time.monotonic()
                rows = client.query_subject(subject)
                latencies.append(time.monotonic() - query_started)
                if len(rows) < 2:
                    raise RuntimeError(f"subject {subject} returned {len(rows)} triples")
            ordered = sorted(latencies)
            value = {"mode": "query", "query_count": args.queries,
                     "elapsed_seconds": time.monotonic() - started,
                     "latency_seconds": {"min": ordered[0], "mean": sum(ordered) / len(ordered),
                                         "p50": ordered[len(ordered)//2],
                                         "p95": ordered[min(len(ordered)-1, int(len(ordered)*.95))],
                                         "max": ordered[-1]}}
        write_json(Path(args.output), value)
    print(json.dumps(value.get("totals", value.get("summary", value.get("metrics"))), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
