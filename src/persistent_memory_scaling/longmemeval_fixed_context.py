"""Gold-blind fixed evidence-token budget comparison on LongMemEval-S."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

import tiktoken


CORE_SYSTEMS = (
    "asm_bridge81",
    "vector_bridge81",
    "bm25_bridge81",
    "vector_bm25_rrf_bridge81",
    "trustgraph_graph_embeddings",
)
ADDITIONAL_SYSTEMS = (
    "asm_vector_rrf_bridge81",
    "asm_bm25_rrf_bridge81",
    "asm_vector_bm25_rrf_bridge81",
    "full_history_canonical",
    "random_history_deterministic",
)
SYSTEMS = (*CORE_SYSTEMS, *ADDITIONAL_SYSTEMS)
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
        separator_tokens = len(encoding.encode("\n\n", disallowed_special=()))
        for item in package.evidence:
            available = self.budget - used - (separator_tokens if kept else 0)
            if available <= 0:
                omitted += 1
                continue
            tokens = encoding.encode(item.content, disallowed_special=())
            selected = tokens[:available]
            content = encoding.decode(selected).strip()
            if not content:
                omitted += 1
                continue
            if kept:
                used += separator_tokens
            used += len(encoding.encode(content, disallowed_special=()))
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
        "asm_vector_rrf_bridge81_gpt4o": "asm_vector_rrf_bridge81",
        "asm_bm25_rrf_bridge81_gpt4o": "asm_bm25_rrf_bridge81",
        "asm_vector_bm25_rrf_bridge81_gpt4o": "asm_vector_bm25_rrf_bridge81",
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


def _resume_protocol_is_compatible(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    """Allow additive systems and the documented fail-closed continuation migration."""
    previous_copy = dict(previous)
    current_copy = dict(current)
    if "reader_failure_policy" in current_copy:
        previous_copy.setdefault("reader_failure_policy", current_copy["reader_failure_policy"])
    previous_systems = set(previous_copy.pop("systems", []))
    current_systems = set(current_copy.pop("systems", []))
    return previous_copy == current_copy and previous_systems <= current_systems


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
    parser.add_argument(
        "--expanded", action="store_true",
        help="after the core matrix completes, add ASM hybrids and non-retrieval controls",
    )
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    sys.path[:0] = [str(args.asm_root), str(args.asm_root / "src")]
    from asm_memory_bridge import OpenAIResponsesReader, ReaderAnswer, RetrievalCandidate
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
    for instance in instances:
        canonical = [memory.memory_id for memory in instance.memories]
        random_order = sorted(
            canonical,
            key=lambda memory_id: hashlib.sha256(
                f"{instance.question_id}\0{memory_id}".encode("utf-8")
            ).hexdigest(),
        )
        rankings.setdefault(instance.question_id, {})["full_history_canonical"] = canonical
        rankings[instance.question_id]["random_history_deterministic"] = random_order
    selected_systems = SYSTEMS if args.expanded else CORE_SYSTEMS
    missing = [
        qid for qid in evaluation_ids
        if not set(selected_systems) <= set(rankings.get(qid, {}))
    ]
    if missing:
        raise ValueError(f"frozen rankings incomplete for {len(missing)} questions")

    protocol = {
        "experiment": "LongMemEval-S fixed evidence-token budget",
        "systems": list(selected_systems),
        "budgets": args.budgets,
        "budget_unit": "o200k_base tokens in joined evidence content",
        "reader": f"openai:{args.reader_model}",
        "same_reader": True,
        "same_questions": True,
        "top_k": 15,
        "rankings_frozen": True,
        "gold_visible_to_ranking_or_budgeting": False,
        "reader_failure_policy": (
            "after configured attempts, preserve raw outputs, record an incorrect "
            "fail-closed row, and continue"
        ),
        "trustgraph_ranking_source": str(args.trustgraph_results.resolve()),
        "note": "The source TrustGraph answers were uncompacted; only their frozen rankings are reused here.",
        "evaluation_question_ids": evaluation_ids,
    }
    rows: list[dict[str, Any]] = []
    if args.resume and args.output.is_file():
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        if not _resume_protocol_is_compatible(dict(previous.get("protocol", {})), protocol):
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
    captured_responses: list[dict[str, Any]] = []
    network_transport = reader._transport

    def capturing_transport(payload: dict[str, Any]) -> dict[str, Any]:
        response = network_transport(payload)
        captured_responses.append(response)
        return response

    reader._transport = capturing_transport

    class RecordedFailureReader:
        def __init__(self, answer: ReaderAnswer) -> None:
            self._answer = answer

        def answer(self, query: Any, evidence: Any) -> ReaderAnswer:
            return self._answer
    total = len(evaluation_ids) * len(selected_systems) * len(args.budgets)
    for question_index, question_id in enumerate(evaluation_ids, 1):
        original = by_id[question_id]
        instance = replace(original, query=replace(original.query, top_k=15))
        for budget in args.budgets:
            compactor = TokenBudgetCompactor(budget)
            for system in selected_systems:
                key = (system, budget, question_id)
                if key in completed:
                    continue
                candidates = tuple(RetrievalCandidate(
                    memory_id=memory_id,
                    score=1.0 / rank,
                    rank=rank,
                    retrieval_reason="frozen gold-blind ranking for fixed-context ablation",
                ) for rank, memory_id in enumerate(rankings[question_id][system], 1))
                captured_responses.clear()
                reader_started = perf_counter()
                try:
                    row = evaluate_one(
                        instance, system, candidates=candidates, reader=reader,
                        max_context_bytes=1_000_000, retrieval_latency_ms=0.0,
                        input_price_per_million=0.0, output_price_per_million=0.0,
                        evidence_transform=compactor,
                    )
                except ReaderError as exc:
                    elapsed_ms = (perf_counter() - reader_started) * 1_000
                    raw_outputs: list[str] = []
                    input_tokens_by_attempt: list[int] = []
                    output_tokens_by_attempt: list[int] = []
                    for response in captured_responses:
                        try:
                            raw_outputs.append(reader._output_text(response))
                        except ReaderError:
                            raw_outputs.append("")
                        usage = response.get("usage", {})
                        usage = usage if isinstance(usage, dict) else {}
                        input_tokens_by_attempt.append(int(usage.get("input_tokens", 0) or 0))
                        output_tokens_by_attempt.append(int(usage.get("output_tokens", 0) or 0))
                    parsed: dict[str, Any] = {}
                    if raw_outputs:
                        try:
                            candidate_output = json.loads(raw_outputs[-1])
                            if isinstance(candidate_output, dict):
                                parsed = candidate_output
                        except json.JSONDecodeError:
                            pass
                    answer_text = parsed.get("answer") if isinstance(parsed.get("answer"), str) else ""
                    cited = parsed.get("cited_memory_ids")
                    cited_ids = tuple(item for item in cited if isinstance(item, str)) if isinstance(cited, list) else ()
                    abstained = parsed.get("abstained") if isinstance(parsed.get("abstained"), bool) else not answer_text
                    if not answer_text and not abstained:
                        abstained = True
                    fallback_answer = ReaderAnswer(
                        answer=answer_text,
                        cited_memory_ids=cited_ids,
                        abstained=abstained,
                        reader_model=f"openai:{args.reader_model}:contract-failure",
                        latency_ms=elapsed_ms,
                        input_tokens=input_tokens_by_attempt[-1] if input_tokens_by_attempt else 0,
                        output_tokens=output_tokens_by_attempt[-1] if output_tokens_by_attempt else 0,
                    )
                    row = evaluate_one(
                        instance, system, candidates=candidates,
                        reader=RecordedFailureReader(fallback_answer),
                        max_context_bytes=1_000_000, retrieval_latency_ms=0.0,
                        input_price_per_million=0.0, output_price_per_million=0.0,
                        evidence_transform=compactor,
                    )
                    row.update({
                        "reader_contract_failure": True,
                        "reader_failure_error": str(exc),
                        "reader_failure_outputs": raw_outputs,
                        "reader_attempts_used": len(captured_responses),
                        "reader_attempt_input_tokens_total": sum(input_tokens_by_attempt),
                        "reader_attempt_output_tokens_total": sum(output_tokens_by_attempt),
                        "invalid_cited_memory_ids": sorted(
                            set(cited_ids) - set(row["evidence_memory_ids"])
                        ),
                    })
                    print(
                        f"[{system}/{budget}/{question_id}] recorded reader contract "
                        f"failure after {len(captured_responses)} attempts; continuing",
                        flush=True,
                    )
                else:
                    row.update({
                        "reader_contract_failure": False,
                        "reader_attempts_used": len(captured_responses),
                        "reader_attempt_input_tokens_total": sum(
                            int((response.get("usage") or {}).get("input_tokens", 0) or 0)
                            for response in captured_responses
                        ),
                        "reader_attempt_output_tokens_total": sum(
                            int((response.get("usage") or {}).get("output_tokens", 0) or 0)
                            for response in captured_responses
                        ),
                    })
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
        for system in selected_systems:
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
