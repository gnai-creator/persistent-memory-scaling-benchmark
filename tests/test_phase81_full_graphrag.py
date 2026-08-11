from __future__ import annotations

from persistent_memory_scaling.trustgraph.phase81_full_graphrag import retry_call, summary


def test_retry_call_recovers_and_reports_attempt_count(monkeypatch) -> None:
    calls = 0

    def operation() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("transient")
        return "ok"

    monkeypatch.setattr("time.sleep", lambda _: None)
    result, attempts = retry_call(
        operation,
        label="test",
        max_attempts=3,
        initial_delay_seconds=0,
        max_delay_seconds=0,
    )
    assert result == "ok"
    assert attempts == 3


def test_retry_call_zero_attempt_limit_keeps_retrying(monkeypatch) -> None:
    calls = 0

    def operation() -> int:
        nonlocal calls
        calls += 1
        if calls < 4:
            raise RuntimeError("transient")
        return calls

    monkeypatch.setattr("time.sleep", lambda _: None)
    result, attempts = retry_call(
        operation,
        label="test",
        max_attempts=0,
        initial_delay_seconds=0,
        max_delay_seconds=0,
    )
    assert result == 4
    assert attempts == 4


def test_summary_reports_longmemeval_recall_at_15() -> None:
    row = {
        "sources_mappable": True,
        "grounding_recall_at_5": False,
        "grounding_recall_at_15": True,
        "source_recall_at_5": False,
        "source_recall_at_15": True,
        "diagnostic_answer_score": 0.5,
        "token_f1": 0.5,
        "answer_containment": False,
        "exact_match": False,
        "full_graphrag_latency_ms": 10.0,
        "input_tokens": 2,
        "output_tokens": 3,
        "explain_replay_latency_ms": 5.0,
    }
    result = summary([row])
    assert result["grounding_recall_at_15"] == 1.0
    assert result["source_recall_at_15"] == 1.0
