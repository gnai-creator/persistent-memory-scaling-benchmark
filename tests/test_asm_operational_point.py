from pathlib import Path

from persistent_memory_scaling.asm_operational_point import extract


def test_extract_builds_measured_single_point() -> None:
    source = {
        "protocol": {"dataset_sha256": "abc", "reader": "reader", "frozen_evaluation_examples": 2},
        "rows": [
            {"system": "asm_compact", "question_id": "q1", "reader_input_tokens": 100,
             "retrieval_recall": 1, "diagnostic_answer_score": .8},
            {"system": "asm_compact", "question_id": "q2", "reader_input_tokens": 300,
             "retrieval_recall": 0, "diagnostic_answer_score": .6},
        ],
    }
    # The extractor hashes its source file for provenance.
    source_path = Path(__file__)
    rows, summary = extract(source, source_path)
    assert len(rows) == 2
    assert summary["reader_context_tokens"]["p50"] == 200
    assert summary["recall_at_5"] == .5
    assert summary["qa_score"] == .7
    assert summary["measurement_status"] == "measured-single-operational-point"
