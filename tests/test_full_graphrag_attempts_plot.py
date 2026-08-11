from __future__ import annotations

from persistent_memory_scaling.trustgraph.full_graphrag_attempts_plot import attempt_series


def test_attempt_series_preserves_missing_legacy_values() -> None:
    questions, graph, explain = attempt_series(
        {
            "rows": [
                {"question_id": "legacy"},
                {
                    "question_id": "retried",
                    "full_graphrag_attempts": 3,
                    "explain_attempts": 1,
                },
            ]
        }
    )
    assert questions == [1, 2]
    assert graph == [None, 3]
    assert explain == [None, 1]
