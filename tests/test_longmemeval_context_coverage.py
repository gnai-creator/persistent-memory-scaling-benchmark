from persistent_memory_scaling.longmemeval_context_coverage import summarize


def test_summarize_reports_distribution() -> None:
    result = summarize([1.0, 2.0, 3.0, 4.0])
    assert result["mean"] == 2.5
    assert result["median"] == 2.5
    assert result["min"] == 1.0
    assert result["max"] == 4.0
