"""Gold-blind fixed evidence-token budget comparison on LongMemEval-S."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import mean
from typing import Any

import tiktoken


SYSTEMS = (
    "asm_bridge81",
    "vector_bridge81",
    "bm25_bridge81",
    "vector_bm25_rrf_bridge81",
    "trustgraph_graph_embeddings",
)
DEFAULT_BUDGETS = (2_000, 4_000, 8_000, 16_000, 28_000)


@dataclass(slots=True)
class TokenBudgetCompactor:
    """Pack ranked evidence without exceeding a content-token budget."""

    budget: int
    encoding_name: str = "o200k_base"
    last_used_tokens: int = 0

    def __post_init__(self) -> None:
        if self.budget < 1:
            raise ValueError("token budget must be positive")

    def compact(self, query: Any, package: Any) -> Any:
        from asm_memory_bridge import Evidence, EvidencePackage

        encoding = tiktoken.get_encoding(self.encoding_name)
        kept: list[Any] = []
        used = 0
        omitted = package.omitted_candidates
        separator_tokens = len(encoding.encode("\n\n"))
        for item in package.evidence:
            available = self.budget - used - (separator_tokens if kept else 0)
            if available <= 0:
                omitted += 1
                continue
            tokens = encoding.encode(item.content)
            selected = tokens[:available]
            content = encoding.decode(selected).strip()
            if not content:
                omitted += 1
                continue
            if kept:
                used += separator_tokens
            used += len(encoding.encode(content))
            kept.append(Evidence(
                memory_id=item.memory_id,
                occurred_at=item.occurred_at,
                content=content,
                source_id=item.source_id,
                score=item.score,
            ))
            if len(selected) < len(tokens):
                omitted += 1
        self.last_used_tokens = used
        return EvidencePackage(
            query_id=package.query_id,
            evidence=tuple(kept),
            omitted_candidates=omitted,
            context_bytes=len("\n\n".join(item.content for item in kept).encode("utf-8")),
            provenance_complete=package.provenance_complete,
        )


def _load_rankings(asm_payload: dict[str, Any], tg_payload: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    aliases = {
        "asm_bridge81_gpt4o": "asm_bridge81",
        "vector_bridge81_gpt4o": "vector_bridge81",
        "bm25_bridge81_gpt4o": "bm25_bridge81",
        "vector_bm25_rrf_bridge81_gpt4o": "vector_bm25_rrf_bridge81",
    }
    rankings: dict[str, dict[str, list[str]]] = {}
    for row in asm_payload["rows"]:
        target = aliases.get(str(row["system"]))
        if target:
            rankings.setdefault(str(row["question_id"]), {})[target] = list(row["retrieved_memory_ids"])
    for row in tg_payload["rows"]:
        rankings.setdefault(str(row["question_id"]), {})["trustgraph_graph_embeddings"] = list(
            row["retrieved_memory_ids"]
        )
    return rankings


def _save(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asm-root", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--oracle-dataset", type=Path, required=True)
    parser.add_argument("--asm-results", type=Path, required=True)
    parser.add_argument("--trustgraph-results", type=Path, required=True)
    parser.add_argument("--official-evaluator-root", type=Path, required=True)
    parser.add_argument("--official-python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budgets", type=int, nargs="+", default=list(DEFAULT_BUDGETS))
    parser.add_argument("--max-examples", type=int, default=0)
    parser.add_argument("--reader-model", default="gpt-4o")
    parser.add_argument("--reader-api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--reader-attempts", type=int, default=5)
    parser.add_argument("--retry-delay-seconds", type=float, default=1.0)
    parser.add_argument("--skip-official-evaluator", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    sys.path[:0] = [str(args.asm_root), str(args.asm_root / "src")]
    from asm_memory_bridge import OpenAIResponsesReader, RetrievalCandidate
    from asm_memory_bridge.errors import ReaderError
    from benchmarks.longmemeval.adapter import load_dataset
    from benchmarks.longmemeval.phase4 import run_official_evaluator
    from benchmarks.multiwoz.phase8 import evaluate_one, metric_summary

    asm_payload = json.loads(args.asm_results.read_text(encoding="utf-8"))
    tg_payload = json.loads(args.trustgraph_results.read_text(encoding="utf-8"))
    rankings = _load_rankings(asm_payload, tg_payload)
    instances = load_dataset(args.dataset)
    evaluation_ids = [str(value) for value in asm_payload["protocol"]["evaluation_question_ids"]]
    if args.max_examples:
        evaluation_ids = evaluation_ids[: args.max_examples]
    by_id = {item.question_id: item for item in instances}
    missing = [qid for qid in evaluation_ids if set(rankings.get(qid, {})) != set(SYSTEMS)]
    if missing:
        raise ValueError(f"frozen rankings incomplete for {len(missing)} questions")

    protocol = {
        "experiment": "LongMemEval-S fixed evidence-token budget",
        "systems": list(SYSTEMS),
        "budgets": args.budgets,
        "budget_unit": "o200k_base tokens in joined evidence content",
        "reader": f"openai:{args.reader_model}",
        "same_reader": True,
        "same_questions": True,
        "top_k": 15,
        "rankings_frozen": True,
        "gold_visible_to_ranking_or_budgeting": False,
        "trustgraph_ranking_source": str(args.trustgraph_results.resolve()),
        "note": "The source TrustGraph answers were uncompacted; only their frozen rankings are reused here.",
        "evaluation_question_ids": evaluation_ids,
    }
    rows: list[dict[str, Any]] = []
    if args.resume and args.output.is_file():
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        if previous.get("protocol") != protocol:
            raise ValueError("cannot resume with a different fixed-context protocol")
        rows = list(previous.get("rows", []))
    completed = {(row["system"], int(row["evidence_token_budget"]), row["question_id"]) for row in rows}
    reader = OpenAIResponsesReader(
        model=args.reader_model,
        api_key=os.environ.get(args.reader_api_key_env),
        base_url="https://api.openai.com/v1",
        timeout_seconds=args.timeout_seconds,
        max_output_tokens=1_024,
        attempts=args.reader_attempts,
        retry_delay_seconds=args.retry_delay_seconds,
    )
    total = len(evaluation_ids) * len(SYSTEMS) * len(args.budgets)
    for question_index, question_id in enumerate(evaluation_ids, 1):
        original = by_id[question_id]
        instance = replace(original, query=replace(original.query, top_k=15))
        for budget in args.budgets:
            compactor = TokenBudgetCompactor(budget)
            for system in SYSTEMS:
                key = (system, budget, question_id)
                if key in completed:
                    continue
                candidates = tuple(RetrievalCandidate(
                    memory_id=memory_id,
                    score=1.0 / rank,
                    rank=rank,
                    retrieval_reason="frozen gold-blind ranking for fixed-context ablation",
                ) for rank, memory_id in enumerate(rankings[question_id][system], 1))
                try:
                    row = evaluate_one(
                        instance, system, candidates=candidates, reader=reader,
                        max_context_bytes=1_000_000, retrieval_latency_ms=0.0,
                        input_price_per_million=0.0, output_price_per_million=0.0,
                        evidence_transform=compactor,
                    )
                except ReaderError as exc:
                    raise SystemExit(f"reader failed for {system}/{budget}/{question_id}: {exc}") from exc
                row["evidence_token_budget"] = budget
                row["evidence_tokens_o200k"] = compactor.last_used_tokens
                rows.append(row)
                _save(args.output, {"protocol": protocol, "rows": rows, "complete": False})
                print(
                    f"[{len(rows)}/{total}] q={question_index}/{len(evaluation_ids)} "
                    f"system={system} budget={budget} input={row['reader_input_tokens']}",
                    flush=True,
                )

    summaries: dict[str, Any] = {}
    hypotheses: dict[str, str] = {}
    output_root = args.output.parent / f"{args.output.stem}-official"
    for budget in args.budgets:
        for system in SYSTEMS:
            name = f"{system}_b{budget}"
            selected = [row for row in rows if row["system"] == system and row["evidence_token_budget"] == budget]
            summaries[name] = metric_summary(selected)
            hypothesis = output_root / "hypotheses" / f"{name}.jsonl"
            hypothesis.parent.mkdir(parents=True, exist_ok=True)
            hypothesis.write_text("".join(json.dumps({
                "question_id": row["question_id"], "hypothesis": row["prediction"]
            }) + "\n" for row in sorted(selected, key=lambda item: item["question_id"])), encoding="utf-8")
            hypotheses[name] = str(hypothesis.resolve())
    official: dict[str, Any] = {"status": "skipped", "results": {}}
    if not args.skip_official_evaluator:
        official = {"status": "completed", "results": run_official_evaluator(
            args.official_evaluator_root.resolve(), hypotheses, args.oracle_dataset.resolve(),
            judge_model="gpt-4o", python_bin=str(args.official_python), output_root=output_root,
        )}
    payload = {
        "protocol": protocol,
        "summary": summaries,
        "official_evaluation": official,
        "complete": len(rows) == total,
        "rows": rows,
    }
    _save(args.output, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
