import pytest

from persistent_memory_scaling.paired_reader_context_scaling import quality_gates, validate_pair
from persistent_memory_scaling.rag_reader_context_scaling_runner import fts_query


def _row(system: str, reader: str = "ollama:qwen3.5:0.8b") -> dict:
    return {"system": system, "history_events": 10_000, "query_id": "q1", "reader_model": reader}


def test_pair_requires_same_keys_and_reader() -> None:
    validate_pair([_row("asm")], [_row("rag")])
    with pytest.raises(ValueError, match="same reader"):
        validate_pair([_row("asm")], [_row("rag", "other")])
    mismatched = {**_row("rag"), "query_id": "q2"}
    with pytest.raises(ValueError, match="same checkpoint"):
        validate_pair([_row("asm")], [mismatched])


def test_fts_query_is_lexical_and_deduplicated() -> None:
    assert fts_query("What was recorded by event 17, event 17?") == '"what" OR "was" OR "recorded" OR "by" OR "event" OR "17"'


def test_quality_gate_requires_both_systems_to_meet_both_floors() -> None:
    summary = {"points": [
        {"system": "asm", "history_events": 10, "recall_at_5": .95, "qa_score": .70},
        {"system": "rag", "history_events": 10, "recall_at_5": .95, "qa_score": .64},
    ]}
    assert quality_gates(summary) == [{"history_events": 10, "passed": False,
                                       "economic_comparison_authorized": False}]
