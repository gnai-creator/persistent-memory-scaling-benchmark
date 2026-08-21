from __future__ import annotations

import pytest

from persistent_memory_scaling.multiwoz_distractors import parse_distractor_checkpoints
from persistent_memory_scaling.multiwoz_paired_runner import (
    multiwoz_answer_quality,
    parse_top_k_values,
    quality_frontier,
)


def test_distractor_checkpoints_allow_zero_and_require_order() -> None:
    assert parse_distractor_checkpoints("0, 100,1000") == [0, 100, 1000]
    with pytest.raises(ValueError):
        parse_distractor_checkpoints("100,0")
    with pytest.raises(ValueError):
        parse_distractor_checkpoints("-1,10")


def test_multiwoz_quality_accepts_any_annotated_slot_value() -> None:
    assert multiwoz_answer_quality("The destination was Cambridge.", "cambridge", False) == 1.0
    assert multiwoz_answer_quality("It was in the north.", "centre, north", False) == 1.0
    assert multiwoz_answer_quality("I cannot answer.", "north", True) == 0.0


def test_top_k_values_are_predeclared_in_increasing_order() -> None:
    assert parse_top_k_values("5,10,20") == [5, 10, 20]
    with pytest.raises(ValueError):
        parse_top_k_values("10,5")


def test_quality_frontier_selects_smallest_eligible_top_k() -> None:
    base = {
        "system": "ASM",
        "history_events": 100,
        "n": 20,
        "context_tokens": {"p50": 100, "p95": 120, "p99": 130, "mean": 105},
    }
    sweep = {"points": [
        {**base, "top_k": 5, "recall_at_5": .80, "qa_score": .70},
        {**base, "top_k": 10, "recall_at_5": .90, "qa_score": .70},
        {**base, "top_k": 20, "recall_at_5": .95, "qa_score": .75},
    ]}
    result = quality_frontier(sweep, recall_floor=.90, qa_floor=.65)
    assert result["points"][0]["top_k"] == 10
