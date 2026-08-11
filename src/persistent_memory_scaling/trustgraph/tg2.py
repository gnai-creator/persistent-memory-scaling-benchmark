"""Deterministic TG-2 workload, resumable ingestion journal and exact audit."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import validate_event, validate_query
from .preflight import write_json

TG2_SEED = 20260811
TG2_SCHEMA = "tg2-workload-v1"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


def _base(seed: int) -> str:
    return f"urn:pmsb:tg2:{seed}"


def _triple(evidence: str, subject: str, predicate: str, obj: str,
            object_type: str = "iri") -> dict[str, str]:
    return {"evidence_id": evidence, "s": subject, "p": predicate,
            "o": obj, "object_type": object_type}


def generate_event(index: int, seed: int = TG2_SEED) -> dict[str, Any]:
    if index < 0:
        raise ValueError("event index must be non-negative")
    base = _base(seed)
    language = "en" if index % 2 == 0 else "pt-BR"
    kind = ("atomic", "temporal", "relational", "multi-hop", "correction",
            "conflict", "duplicate", "distractor")[index % 8]
    event_id = f"tg2-{seed}-event-{index:09d}"
    evidence = f"tg2-{seed}-evidence-{index:09d}"
    event_iri = f"{base}:event:{index:09d}"
    person = f"{base}:person:{index:09d}"
    triples = [
        _triple(evidence, event_iri, RDF_TYPE, f"{base}:Event"),
        _triple(evidence, event_iri, f"{base}:sequence", str(index), "literal"),
        _triple(evidence, event_iri, f"{base}:kind", kind, "literal"),
        _triple(evidence, event_iri, f"{base}:evidence-id", evidence, "literal"),
        _triple(evidence, event_iri, f"{base}:about", person),
    ]
    if kind == "atomic":
        triples.append(_triple(evidence, person, f"{base}:prefers", f"Topic-{index % 97}", "literal"))
    elif kind == "temporal":
        triples += [_triple(evidence, person, f"{base}:role", f"Role-{index % 31}", "literal"),
                    _triple(evidence, event_iri, f"{base}:effective-day", f"2026-{index % 12 + 1:02d}-{index % 28 + 1:02d}", "literal")]
    elif kind == "relational":
        triples.append(_triple(evidence, person, f"{base}:knows", f"{base}:person:{(index + 17) % 1_000_000:09d}"))
    elif kind == "multi-hop":
        city = f"{base}:city:{index % 1000:04d}"
        triples += [_triple(evidence, person, f"{base}:lives-in", city),
                    _triple(evidence, city, f"{base}:in-country", f"{base}:country:{index % 25:02d}")]
    elif kind == "correction":
        profile = f"{base}:profile:{index // 16:09d}"
        revision = (index // 8) % 2
        triples += [_triple(evidence, person, f"{base}:profile", profile),
                    _triple(evidence, profile, f"{base}:corrected-status",
                            "superseded" if revision == 0 else "current", "literal")]
    elif kind == "conflict":
        claim = f"{base}:claim:{index // 16:09d}"
        alternative = (index // 8) % 2
        triples += [_triple(evidence, claim, f"{base}:subject", person),
                    _triple(evidence, claim, f"{base}:claimed-value", f"Value-{alternative}", "literal"),
                    _triple(evidence, claim, f"{base}:source", f"{base}:source:{alternative}")]
    elif kind == "duplicate":
        # Each consecutive pair repeats one identical payload triple while its
        # two event/provenance records remain independently traceable.
        group = index // 16
        triples.append(_triple(evidence, f"{base}:duplicate-subject:{group:09d}",
                               f"{base}:duplicate-value", f"Value-{group % 19}", "literal"))
    else:
        triples.append(_triple(evidence, person, f"{base}:noise", f"Distractor-{index:09d}", "literal"))
    text = (f"Event {index} records a {kind} fact."
            if language == "en" else f"O evento {index} registra um fato {kind}.")
    return validate_event({
        "schema_version": "tg-event-v1", "event_id": event_id, "sequence": index,
        "namespace": f"tg2-{seed}", "language": language, "text": text,
        "triples": triples, "entity_contexts": [], "relevant_evidence_ids": [evidence],
    })


def iter_events(event_count: int, seed: int = TG2_SEED, start: int = 0) -> Iterator[dict[str, Any]]:
    if event_count < 0 or start < 0 or start > event_count:
        raise ValueError("invalid event range")
    for index in range(start, event_count):
        yield generate_event(index, seed)


def generate_queries(event_count: int, seed: int = TG2_SEED, count: int = 80) -> list[dict[str, Any]]:
    if event_count <= 0 or count <= 0:
        raise ValueError("event_count and query count must be positive")
    queries = []
    for number in range(count):
        target = (number * 104729 + seed) % event_count
        event = generate_event(target, seed)
        language = event["language"]
        queries.append(validate_query({
            "schema_version": "tg-query-v1", "query_id": f"tg2-{seed}-query-{number:04d}",
            "namespace": f"tg2-{seed}", "language": language,
            "question": (f"What was recorded by event {target}?" if language == "en"
                         else f"O que foi registrado pelo evento {target}?"),
            "query_type": event["triples"][-1]["p"].rsplit(":", 1)[-1],
            "expected_answer": event["triples"][-1]["o"],
            "relevant_evidence_ids": event["relevant_evidence_ids"], "should_abstain": False,
        }))
    return queries


def workload_fingerprint(event_count: int, seed: int = TG2_SEED) -> str:
    digest = hashlib.sha256(f"{TG2_SCHEMA}\0{seed}\0{event_count}\n".encode())
    for event in iter_events(event_count, seed):
        digest.update(json.dumps(event, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def workload_descriptor(event_count: int, seed: int = TG2_SEED) -> dict[str, Any]:
    counts = {kind: 0 for kind in ("atomic", "temporal", "relational", "multi-hop",
                                   "correction", "conflict", "duplicate", "distractor")}
    triple_count = 0
    for event in iter_events(event_count, seed):
        counts[event["triples"][2]["o"]] += 1
        triple_count += len(event["triples"])
    return {"schema_version": TG2_SCHEMA, "seed": seed, "event_count": event_count,
            "triple_count": triple_count, "category_counts": counts,
            "languages": ["en", "pt-BR"], "sha256": workload_fingerprint(event_count, seed)}


@dataclass
class IngestionJournal:
    path: Path
    workload_sha256: str
    event_count: int
    chunk_size: int

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": "tg2-journal-v1", "workload_sha256": self.workload_sha256,
                    "event_count": self.event_count, "chunk_size": self.chunk_size,
                    "completed_chunks": []}
        value = json.loads(self.path.read_text(encoding="utf-8"))
        expected = (self.workload_sha256, self.event_count, self.chunk_size)
        actual = (value.get("workload_sha256"), value.get("event_count"), value.get("chunk_size"))
        if actual != expected:
            raise ValueError("journal does not match frozen workload")
        return value

    def mark_complete(self, chunk_index: int) -> None:
        value = self.load()
        completed = set(value["completed_chunks"])
        completed.add(chunk_index)
        value["completed_chunks"] = sorted(completed)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        write_json(temporary, value)
        temporary.replace(self.path)


def ingest_resumable(client: Any, event_count: int, journal: IngestionJournal,
                     seed: int = TG2_SEED) -> dict[str, int]:
    state = journal.load()
    completed = set(state["completed_chunks"])
    imported_events = skipped_events = 0
    chunks = (event_count + journal.chunk_size - 1) // journal.chunk_size
    for chunk_index in range(chunks):
        start = chunk_index * journal.chunk_size
        end = min(event_count, start + journal.chunk_size)
        if chunk_index in completed:
            skipped_events += end - start
            continue
        events = list(iter_events(end, seed, start))
        client.import_structured_events(events, document_id=f"tg2-chunk-{chunk_index:08d}")
        last_subject = events[-1]["triples"][0]["s"]
        client.wait_for_subject(last_subject, 5, 300)
        journal.mark_complete(chunk_index)
        imported_events += len(events)
    return {"imported_events": imported_events, "skipped_events": skipped_events, "chunks": chunks}


def _canonical(triple: tuple[str, str, str]) -> str:
    return json.dumps(triple, ensure_ascii=False, separators=(",", ":"))


def audit_export(client: Any, event_count: int, database: Path,
                 seed: int = TG2_SEED) -> dict[str, int | bool]:
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE expected (triple TEXT PRIMARY KEY)")
        connection.execute("CREATE TABLE actual (triple TEXT PRIMARY KEY)")
        for event in iter_events(event_count, seed):
            connection.executemany("INSERT OR IGNORE INTO expected VALUES (?)",
                                   [(_canonical((item["s"], item["p"], item["o"])),)
                                    for item in event["triples"]])
        unexpected = duplicate_exports = 0
        for item in client.export_triples():
            value = _canonical((str(item.s), str(item.p), str(item.o)))
            if not connection.execute("SELECT 1 FROM expected WHERE triple = ?", (value,)).fetchone():
                unexpected += 1
            try:
                connection.execute("INSERT INTO actual VALUES (?)", (value,))
            except sqlite3.IntegrityError:
                duplicate_exports += 1
        missing = connection.execute(
            "SELECT count(*) FROM expected e LEFT JOIN actual a USING (triple) WHERE a.triple IS NULL"
        ).fetchone()[0]
        expected = connection.execute("SELECT count(*) FROM expected").fetchone()[0]
        actual = connection.execute("SELECT count(*) FROM actual").fetchone()[0]
        return {"valid": missing == 0 and unexpected == 0 and duplicate_exports == 0,
                "expected_unique_triples": expected, "actual_unique_triples": actual,
                "missing": missing, "unexpected": unexpected, "duplicate_exports": duplicate_exports}
    finally:
        connection.close()


def export_cassandra_collection(collection: str) -> Iterator[Any]:
    """Stream the exact collection partition when SDK bulk export never closes."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", collection):
        raise ValueError("unsafe collection identifier")
    statement = ("PAGING OFF; SELECT JSON s,p,o FROM default.quads_by_collection "
                 f"WHERE collection='{collection}';")
    process = subprocess.Popen(
        ["docker", "exec", "generated-cassandra-1", "cqlsh", "-e", statement],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    assert process.stdout is not None
    for line in process.stdout:
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        value = json.loads(stripped)
        yield type("ExportedTriple", (), value)()
    stderr = process.stderr.read() if process.stderr else ""
    if process.wait() != 0:
        raise RuntimeError(stderr.strip() or "Cassandra collection export failed")
