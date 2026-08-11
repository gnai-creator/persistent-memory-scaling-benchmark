"""Run ASM Memory Bridge Phase 8.1 with external process-level accounting."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def _processes() -> dict[int, dict]:
    result: dict[int, dict] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            status = (entry / "status").read_text(errors="replace").splitlines()
            values = {line.split(":", 1)[0]: line.split(":", 1)[1].strip()
                      for line in status if ":" in line}
            cmdline = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            stat = (entry / "stat").read_text().split()
            result[int(entry.name)] = {
                "ppid": int(values.get("PPid", "0")),
                "rss_bytes": int(values.get("VmRSS", "0 kB").split()[0]) * 1024,
                "cpu_ticks": int(stat[13]) + int(stat[14]),
                "cmdline": cmdline,
            }
        except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError, IndexError):
            continue
    return result


def _descendants(root: int, processes: dict[int, dict]) -> set[int]:
    selected = {root}
    changed = True
    while changed:
        changed = False
        for pid, row in processes.items():
            if row["ppid"] in selected and pid not in selected:
                selected.add(pid)
                changed = True
    return selected


def _gpu_by_pid() -> dict[int, int]:
    completed = subprocess.run([
        "nvidia-smi", "--query-compute-apps=pid,used_gpu_memory", "--format=csv,noheader,nounits"
    ], capture_output=True, text=True, check=False)
    values: dict[int, int] = {}
    if completed.returncode == 0:
        for line in completed.stdout.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) == 2 and all(part.isdigit() for part in parts):
                values[int(parts[0])] = int(parts[1]) * 1024**2
    return values


def _sample(root: int, reader_pattern: str) -> dict:
    processes = _processes()
    tree = _descendants(root, processes)
    reader_roots = {pid for pid, row in processes.items() if reader_pattern in row["cmdline"]}
    readers: set[int] = set()
    for reader_root in reader_roots:
        readers.update(_descendants(reader_root, processes))
    gpu = _gpu_by_pid()
    return {
        "elapsed_monotonic": time.monotonic(),
        "bridge_pids": sorted(tree),
        "bridge_rss_bytes": sum(processes[pid]["rss_bytes"] for pid in tree if pid in processes),
        "bridge_cpu_ticks": sum(processes[pid]["cpu_ticks"] for pid in tree if pid in processes),
        "bridge_vram_bytes": sum(gpu.get(pid, 0) for pid in tree),
        "reader_pids": sorted(readers),
        "reader_rss_bytes": sum(processes[pid]["rss_bytes"] for pid in readers),
        "reader_vram_bytes": sum(gpu.get(pid, 0) for pid in readers),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--reader-pattern", default="ollama serve")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("command required after --")

    baseline_processes = _processes()
    baseline_reader_roots = {pid for pid, row in baseline_processes.items()
                             if args.reader_pattern in row["cmdline"]}
    baseline_readers: set[int] = set()
    for reader_root in baseline_reader_roots:
        baseline_readers.update(_descendants(reader_root, baseline_processes))
    baseline_gpu = _gpu_by_pid()
    baseline = {
        "reader_pids": sorted(baseline_readers),
        "reader_rss_bytes": sum(baseline_processes[pid]["rss_bytes"] for pid in baseline_readers),
        "reader_vram_bytes": sum(baseline_gpu.get(pid, 0) for pid in baseline_readers),
    }
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    process = subprocess.Popen(command, cwd=args.cwd)
    samples = []
    while process.poll() is None:
        samples.append(_sample(process.pid, args.reader_pattern))
        time.sleep(args.interval)
    samples.append(_sample(process.pid, args.reader_pattern))
    ended = time.monotonic()

    def peak(key: str) -> int:
        return max((int(row[key]) for row in samples), default=0)

    result = {
        "schema_version": "asm-phase81-resource-window-v1",
        "started_at": started_at,
        "duration_seconds": ended - started,
        "exit_code": process.returncode,
        "command": command,
        "cwd": str(args.cwd.resolve()),
        "sample_interval_seconds": args.interval,
        "sample_count": len(samples),
        "baseline": baseline,
        "summary": {
            "bridge_rss_peak_bytes": peak("bridge_rss_bytes"),
            "bridge_vram_peak_bytes": peak("bridge_vram_bytes"),
            "reader_rss_peak_bytes": peak("reader_rss_bytes"),
            "reader_vram_peak_bytes": peak("reader_vram_bytes"),
            "reader_rss_incremental_peak_bytes": max(0, peak("reader_rss_bytes") - baseline["reader_rss_bytes"]),
            "reader_vram_incremental_peak_bytes": max(0, peak("reader_vram_bytes") - baseline["reader_vram_bytes"]),
        },
        "samples": samples,
        "notes": [
            "Bridge values include only the launched process tree.",
            "Reader values are separate because Ollama is a shared external service.",
            "Concurrent ASM training is excluded from both classifications.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return int(process.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
