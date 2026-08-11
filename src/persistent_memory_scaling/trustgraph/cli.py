"""TG-0 command-line harness."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .client import TrustGraphClient
from .contracts import validate_manifest
from .preflight import collect_preflight, sha256_file, write_json
from .workload import BASE, generate_smoke_workload


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def generate(args: argparse.Namespace) -> int:
    workload = generate_smoke_workload()
    output = Path(args.output)
    write_json(output, workload)
    print(f"wrote {len(workload['events'])} events and {len(workload['queries'])} queries to {output}")
    print(workload["sha256"])
    return 0


def preflight(args: argparse.Namespace) -> int:
    report = collect_preflight(Path(args.compose), Path(args.upstream))
    write_json(Path(args.output), report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["docker"].get("returncode") == 0 else 2


def smoke(args: argparse.Namespace) -> int:
    token = args.token or os.getenv("TRUSTGRAPH_TOKEN")
    if not token:
        raise SystemExit("TRUSTGRAPH_TOKEN or --token is required")

    workload_path = Path(args.workload)
    workload = json.loads(workload_path.read_text(encoding="utf-8"))
    if len(workload["events"]) != 100:
        raise SystemExit("TG-0 requires exactly 100 events")

    client = TrustGraphClient(
        url=args.url,
        token=token,
        workspace=args.workspace,
        flow_id=args.flow_id,
        collection=args.collection,
    )
    client.start_flow(model=args.model, embeddings_model=args.embeddings_model)
    imported = 300 if args.skip_import else client.import_events(workload["events"])
    if not args.skip_document:
        document_text = "\n".join(event["text"] for event in workload["events"])
        client.load_text(document_text, document_id=f"{args.run_id}-events")
    first = client.wait_for_subject(f"{BASE}:person:000", minimum=2, timeout=args.timeout)
    last = client.wait_for_subject(f"{BASE}:person:099", minimum=2, timeout=args.timeout)

    graph_result = client.graph_rag(workload["queries"][0]["question"])
    document_result = client.wait_for_document_rag(
        workload["queries"][0]["question"], timeout=args.timeout
    )
    result = {
        "schema_version": "tg-smoke-result-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "imported_triples": imported,
        "first_subject_triples": len(first),
        "last_subject_triples": len(last),
        "graph_rag_text": getattr(graph_result, "text", str(graph_result)),
        "document_rag_text": getattr(document_result, "text", str(document_result)),
    }
    output = Path(args.output)
    write_json(output, result)

    manifest = validate_manifest({
        "schema_version": "tg-run-manifest-v1",
        "run_id": args.run_id,
        "created_at": result["created_at"],
        "phase": "TG-0",
        "status": "completed",
        "seed": workload["seed"],
        "event_count": len(workload["events"]),
        "query_count": len(workload["queries"]),
        "workspace": args.workspace,
        "collection": args.collection,
        "flow_id": args.flow_id,
        "upstream": {"repository": "https://github.com/trustgraph-ai/trustgraph.git", "commit": args.upstream_commit},
        "deployment": {"trustgraph_image_version": "2.8.12", "compose_sha256": sha256_file(Path(args.compose))},
        "models": {"llm": args.model, "embeddings": args.embeddings_model, "reranker": "ms-marco-MiniLM-L-12-v2"},
        "hardware": {"preflight": args.preflight},
        "artifacts": {"workload": str(workload_path), "result": str(output)},
    })
    write_json(Path(args.manifest), manifest)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def parser() -> argparse.ArgumentParser:
    root = _root()
    generated = root / "configs/trustgraph/generated"
    cli = argparse.ArgumentParser(prog="pmsb-tg0")
    commands = cli.add_subparsers(dest="command", required=True)

    gen = commands.add_parser("generate", help="generate the frozen 100-event workload")
    gen.add_argument("--output", default=str(root / "workloads/synthetic/tg0-smoke.json"))
    gen.set_defaults(func=generate)

    check = commands.add_parser("preflight", help="collect read-only host/deployment facts")
    check.add_argument("--compose", default=str(generated / "docker-compose.yaml"))
    check.add_argument("--upstream", default=str(root.parent / "trustgraph"))
    check.add_argument("--output", default=str(root / "manifests/tg0-preflight.json"))
    check.set_defaults(func=preflight)

    run = commands.add_parser("smoke", help="run the TG-0 TrustGraph smoke")
    run.add_argument("--url", default="http://localhost:8888/")
    run.add_argument("--token")
    run.add_argument("--workspace", default="default")
    run.add_argument("--collection", default="tg0-smoke")
    run.add_argument("--flow-id", default="tg0-smoke")
    run.add_argument("--model", default="qwen2.5:0.5b")
    run.add_argument("--embeddings-model", default="sentence-transformers/all-MiniLM-L6-v2")
    run.add_argument("--timeout", type=float, default=300)
    run.add_argument(
        "--skip-import",
        action="store_true",
        help="resume after a confirmed bulk import without writing the triples again",
    )
    run.add_argument(
        "--skip-document",
        action="store_true",
        help="resume after the Librarian document was confirmed as accepted",
    )
    run.add_argument("--run-id", required=True)
    run.add_argument("--workload", default=str(root / "workloads/synthetic/tg0-smoke.json"))
    run.add_argument("--output", required=True)
    run.add_argument("--manifest", required=True)
    run.add_argument("--compose", default=str(generated / "docker-compose.yaml"))
    run.add_argument("--preflight", default=str(root / "manifests/tg0-preflight.json"))
    run.add_argument("--upstream-commit", default="0bcfe9377c3d55b7199c16335b9e52ed91286233")
    run.set_defaults(func=smoke)
    return cli


def main() -> int:
    args = parser().parse_args()
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
