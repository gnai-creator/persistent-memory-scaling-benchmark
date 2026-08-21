import pytest

from persistent_memory_scaling.reader_context_scaling import aggregate, percentile


def test_percentile_interpolates() -> None:
    assert percentile([1, 2, 3, 4], .5) == 2.5
    assert percentile([1, 2, 3, 4], .95) == pytest.approx(3.85)


def test_aggregate_reports_context_distribution_and_quality() -> None:
    rows = [
        {"system": "asm", "history_events": 10_000, "reader_context_tokens": tokens,
         "recall_at_5": recall, "qa_score": qa}
        for tokens, recall, qa in ((100, 1, .8), (200, 0, .6), (300, 1, .7), (400, 1, .9))
    ]
    point = aggregate(rows)["points"][0]
    assert point["context_tokens"]["p50"] == 250
    assert point["context_tokens"]["p95"] == pytest.approx(385)
    assert point["context_tokens"]["p99"] == pytest.approx(397)
    assert point["recall_at_5"] == .75
    assert point["qa_score"] == pytest.approx(.75)


def test_aggregate_reports_reader_contract_failure_rate_when_available() -> None:
    rows = [
        {"system": "asm", "history_events": 10, "reader_context_tokens": 100,
         "recall_at_5": 1, "qa_score": 0, "reader_contract_failure": failed}
        for failed in (True, False)
    ]
    assert aggregate(rows)["points"][0]["reader_contract_failure_rate"] == .5


def test_aggregate_rejects_quality_outside_unit_interval() -> None:
    with pytest.raises(ValueError, match="qa_score outside"):
        aggregate([{"system": "x", "history_events": 1, "reader_context_tokens": 1,
                    "recall_at_5": 1, "qa_score": 50}])
