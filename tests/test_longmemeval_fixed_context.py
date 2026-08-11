from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

ASM_ROOT = Path("/home/felipe/dev/ai/gitlab/asm-memory-bridge")
sys.path[:0] = [str(ASM_ROOT), str(ASM_ROOT / "src")]

from asm_memory_bridge import Evidence, EvidencePackage, MemoryQuery
from persistent_memory_scaling.longmemeval_fixed_context import TokenBudgetCompactor


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
