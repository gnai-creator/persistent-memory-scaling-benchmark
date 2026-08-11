"""Read-only publication gate for the final benchmark artifacts."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Check:
    artifact_id: str
    path: str
    status: str
    detail: str


def _nested(value: dict[str, Any], dotted: str) -> Any:
    current: Any = value
    for key in dotted.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _declares_complete(data: dict[str, Any]) -> bool:
    candidates = (
        _nested(data, "decision.complete"),
        _nested(data, "decision.run_complete"),
        _nested(data, "decision.criteria.complete_frozen_partition"),
        _nested(data, "result.complete"),
        data.get("complete"),
    )
    return any(value is True for value in candidates)


def _rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = data.get("rows")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    result_rows = _nested(data, "result.rows")
    if isinstance(result_rows, list):
        return [row for row in result_rows if isinstance(row, dict)]
    return []


def inspect_artifact(root: Path, spec: dict[str, Any], expected: int) -> Check:
    relative = spec["path"]
    path = (root / relative).resolve()
    if not path.exists():
        return Check(spec["id"], relative, "missing", "file does not exist")
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return Check(spec["id"], relative, "invalid", str(exc))

    kind = spec["kind"]
    rows = _rows(data)
    if kind == "single_system_rows":
        system = spec["system"]
        count = sum(row.get("system") == system for row in rows)
        status = "ready" if count == expected else "running"
        return Check(spec["id"], relative, status, f"{count}/{expected} rows for {system}")

    if kind == "multi_system_rows":
        systems = _nested(data, spec["systems_from"])
        if not isinstance(systems, list) or not systems:
            return Check(spec["id"], relative, "invalid", "expected system list is absent")
        counts = Counter(row.get("system") for row in rows)
        incomplete = [f"{system}={counts[system]}/{expected}" for system in systems if counts[system] != expected]
        if incomplete:
            return Check(spec["id"], relative, "running", ", ".join(incomplete))
        return Check(spec["id"], relative, "ready", f"{len(systems)} systems × {expected} rows")

    if kind in {"trustgraph_rows", "trustgraph_result"}:
        count = len(rows)
        if not count:
            count = int(_nested(data, "result.examples") or _nested(data, "result.completed") or 0)
        complete = _declares_complete(data) or count == expected
        status = "ready" if complete and count == expected else "incomplete"
        return Check(spec["id"], relative, status, f"{count}/{expected} questions")

    if kind == "complete_result":
        summary_examples = _nested(data, "summary.examples")
        if summary_examples is None and isinstance(data.get("summary"), dict):
            values = [item.get("examples") for item in data["summary"].values() if isinstance(item, dict)]
            summary_examples = min(values) if values else None
        count = int(summary_examples or 0)
        declared = _declares_complete(data)
        status = "ready" if declared and count == expected else "incomplete"
        return Check(spec["id"], relative, status, f"complete={declared}; examples={count}/{expected}")

    return Check(spec["id"], relative, "invalid", f"unknown kind: {kind}")


def audit(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    protocols = []
    for protocol in config["protocols"]:
        checks = [inspect_artifact(root, spec, protocol["expected_questions"]) for spec in protocol["artifacts"]]
        protocols.append({
            "id": protocol["id"],
            "label": protocol["label"],
            "expected_questions": protocol["expected_questions"],
            "ready": all(check.status == "ready" for check in checks),
            "artifacts": [check.__dict__ for check in checks],
        })
    return {
        "schema_version": 1,
        "benchmark_ready": all(protocol["ready"] for protocol in protocols),
        "protocols": protocols,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Final benchmark release gate",
        "",
        f"Overall status: **{'READY' if report['benchmark_ready'] else 'NOT READY'}**",
        "",
        "This report is generated from artifacts only. It does not start, stop, or modify benchmark processes.",
        "",
    ]
    for protocol in report["protocols"]:
        lines.extend([
            f"## {protocol['label']}",
            "",
            f"Protocol status: **{'READY' if protocol['ready'] else 'NOT READY'}**",
            "",
            "| Artifact | Status | Evidence |",
            "|---|---:|---|",
        ])
        for artifact in protocol["artifacts"]:
            lines.append(f"| `{artifact['artifact_id']}` | {artifact['status']} | {artifact['detail']} |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/finalization.json"))
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    root = args.config.resolve().parents[1]
    report = audit(root, json.loads(args.config.read_text()))
    output = markdown(report)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(output)
    if not args.json and not args.markdown:
        print(output)
    return 0 if report["benchmark_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
