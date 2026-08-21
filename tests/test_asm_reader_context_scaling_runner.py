import argparse

import pytest

from persistent_memory_scaling.asm_reader_context_scaling_runner import answer_quality, parse_checkpoints


def test_parse_checkpoints_requires_strictly_increasing_unique_values() -> None:
    assert parse_checkpoints("10000,100000,1000000") == [10_000, 100_000, 1_000_000]
    with pytest.raises(argparse.ArgumentTypeError):
        parse_checkpoints("100,10")
    with pytest.raises(argparse.ArgumentTypeError):
        parse_checkpoints("100,100")


def test_answer_quality_is_normalized_containment_and_abstention_fails() -> None:
    assert answer_quality("The answer is Topic-17.", "topic-17", False) == 1.0
    assert answer_quality("Something else", "topic-17", False) == 0.0
    assert answer_quality("topic-17", "topic-17", True) == 0.0
