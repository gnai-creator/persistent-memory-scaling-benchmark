from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

ASM_ROOT = Path("/home/felipe/dev/ai/gitlab/asm-memory-bridge")
sys.path[:0] = [str(ASM_ROOT), str(ASM_ROOT / "src")]

from asm_memory_bridge import Evidence, EvidencePackage, MemoryQuery
from persistent_memory_scaling.longmemeval_fixed_context import (
    TokenBudgetCompactor,
    _is_resumable_row,
    _resume_protocol_is_compatible,
    _seed_rows,
)


def test_token_budget_compactor_never_exceeds_budget() -> None:
    now = datetime.now(UTC)
    package = EvidencePackage(
        query_id="query:test",
        evidence=tuple(Evidence(
            memory_id=f"memory:{index}", occurred_at=now,
            content=("relevant conversation text " * 100), source_id=f"source:{index}", score=1.0,
        ) for index in range(3)),
        omitted_candidates=0, context_bytes=10_000, provenance_complete=True,
    )
    query = MemoryQuery(
        query_id="query:test", namespace_id="namespace:test", requester_id="namespace:test",
        question="What happened?", asked_at=now,
    )
    compactor = TokenBudgetCompactor(200)
    compacted = compactor.compact(query, package)
    assert compactor.last_used_tokens <= 200
    assert compacted.evidence
    assert compacted.context_bytes > 0


def test_resume_accepts_only_additional_systems() -> None:
    previous = {"budgets": [2000], "systems": ["asm", "vector"]}
    expanded = {"budgets": [2000], "systems": ["asm", "vector", "hybrid"]}
    changed = {"budgets": [4000], "systems": ["asm", "vector", "hybrid"]}
    assert _resume_protocol_is_compatible(previous, expanded)
    assert not _resume_protocol_is_compatible(previous, changed)


def test_infrastructure_quota_failure_is_not_resumable() -> None:
    assert _is_resumable_row({"reader_failure_error": "reader output is not valid JSON"})
    assert not _is_resumable_row({
        "reader_failure_error": "HTTP 429: credit_balance_exhausted: insufficient_quota",
    })


def test_seed_rows_filters_budget_system_question_and_quota_failures() -> None:
    valid = {
        "system": "asm", "evidence_token_budget": 2000,
        "question_id": "q1", "reader_failure_error": "",
    }
    payload = {"rows": [
        valid,
        {**valid, "evidence_token_budget": 4000},
        {**valid, "system": "vector"},
        {**valid, "question_id": "q2"},
        {**valid, "reader_failure_error": "You have no credits remaining"},
    ]}
    assert _seed_rows(
        payload, systems=("asm",), budgets=[2000], evaluation_ids=["q1"],
    ) == [valid]
