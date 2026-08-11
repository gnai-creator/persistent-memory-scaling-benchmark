import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from persistent_memory_scaling.trustgraph.tg2 import (
    IngestionJournal,
    audit_export,
    generate_event,
    generate_queries,
    ingest_resumable,
    iter_events,
    workload_descriptor,
    workload_fingerprint,
    export_cassandra_collection,
)
from persistent_memory_scaling.trustgraph.tg2_runner import aggregate_tg2_cycles


def triples(events):
    return {(item["s"], item["p"], item["o"]) for event in events for item in event["triples"]}


def test_generator_is_deterministic_bilingual_and_balanced():
    first = list(iter_events(16))
    second = list(iter_events(16))
    assert first == second
    assert {event["language"] for event in first} == {"en", "pt-BR"}
    assert {event["triples"][2]["o"] for event in first} == {
        "atomic", "temporal", "relational", "multi-hop", "correction",
        "conflict", "duplicate", "distractor",
    }
    keys = ("s", "p", "o", "object_type")
    assert tuple(first[6]["triples"][-1][key] for key in keys) == tuple(
        first[14]["triples"][-1][key] for key in keys
    )


def test_descriptor_and_fingerprint_are_frozen():
    descriptor = workload_descriptor(16)
    assert descriptor["event_count"] == 16
    assert descriptor["triple_count"] == sum(len(event["triples"]) for event in iter_events(16))
    assert descriptor["sha256"] == workload_fingerprint(16)
    assert workload_fingerprint(16) != workload_fingerprint(17)


def test_queries_are_deterministic_and_in_range():
    queries = generate_queries(100, count=20)
    assert queries == generate_queries(100, count=20)
    assert len({item["query_id"] for item in queries}) == 20


class FakeClient:
    def __init__(self):
        self.imports = []

    def import_structured_events(self, events, document_id, include_contexts=False):
        self.imports.extend(events)

    def wait_for_subject(self, subject, minimum, timeout):
        return [object()] * minimum

    def export_triples(self):
        for subject, predicate, obj in sorted(triples(self.imports)):
            yield SimpleNamespace(s=subject, p=predicate, o=obj)


def test_journal_resume_skips_completed_chunks(tmp_path: Path):
    client = FakeClient()
    fingerprint = workload_fingerprint(5)
    journal = IngestionJournal(tmp_path / "journal.json", fingerprint, 5, 2)
    first = ingest_resumable(client, 5, journal)
    second = ingest_resumable(client, 5, journal)
    assert first == {"imported_events": 5, "skipped_events": 0, "chunks": 3}
    assert second == {"imported_events": 0, "skipped_events": 5, "chunks": 3}
    assert json.loads(journal.path.read_text())["completed_chunks"] == [0, 1, 2]


def test_journal_rejects_different_workload(tmp_path: Path):
    path = tmp_path / "journal.json"
    IngestionJournal(path, "a", 2, 1).mark_complete(0)
    with pytest.raises(ValueError, match="frozen workload"):
        IngestionJournal(path, "b", 2, 1).load()


def test_exact_export_audit_detects_missing_and_unexpected(tmp_path: Path):
    client = FakeClient()
    client.imports = list(iter_events(4))
    valid = audit_export(client, 4, tmp_path / "valid.sqlite")
    assert valid["valid"] is True
    client.imports.pop()
    invalid = audit_export(client, 4, tmp_path / "invalid.sqlite")
    assert invalid["valid"] is False
    assert invalid["missing"] > 0


def test_negative_event_index_is_rejected():
    with pytest.raises(ValueError):
        generate_event(-1)


def test_cassandra_export_rejects_unsafe_collection():
    with pytest.raises(ValueError, match="unsafe"):
        list(export_cassandra_collection("collection'; DROP TABLE x;--"))


def test_tg2_aggregate_rejects_mixed_checkpoints():
    values = [{"valid": True, "checkpoint_events": count,
               "workload": {"sha256": "a"}} for count in (100, 1000)]
    with pytest.raises(ValueError, match="share checkpoint"):
        aggregate_tg2_cycles(values)
