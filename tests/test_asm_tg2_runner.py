from persistent_memory_scaling.asm_tg2_runner import canonical_event_content, percentile
from persistent_memory_scaling.trustgraph.tg2 import generate_event


def test_canonical_event_content_preserves_tg2_identity_and_evidence() -> None:
    event = generate_event(17)
    content = canonical_event_content(event)
    assert event["event_id"] in content
    assert event["relevant_evidence_ids"][0] in content
    assert event["triples"][-1]["o"] in content


def test_percentile_interpolates() -> None:
    assert percentile([1.0, 2.0, 3.0, 4.0], .5) == 2.5
