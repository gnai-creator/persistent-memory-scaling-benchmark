"""Deterministic bilingual TG-0 smoke workload."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .contracts import validate_event, validate_query

BASE = "urn:pmsb:tg0"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
LIVES_IN = f"{BASE}:lives-in"


def _fingerprint(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def generate_smoke_workload(event_count: int = 100, seed: int = 20260811) -> dict[str, Any]:
    if event_count != 100:
        raise ValueError("TG-0 smoke is frozen at exactly 100 events")

    events: list[dict[str, Any]] = []
    for index in range(event_count):
        language = "en" if index % 2 == 0 else "pt-BR"
        person = f"Person-{index:03d}"
        city = f"City-{index % 10:02d}"
        person_iri = f"{BASE}:person:{index:03d}"
        city_iri = f"{BASE}:city:{index % 10:02d}"
        evidence_id = f"tg0-evidence-{index:03d}"
        text = (
            f"{person} lives in {city}."
            if language == "en"
            else f"{person} mora em {city}."
        )
        event = {
            "schema_version": "tg-event-v1",
            "event_id": f"tg0-event-{index:03d}",
            "sequence": index,
            "namespace": "tg0-smoke",
            "language": language,
            "text": text,
            "triples": [
                {
                    "evidence_id": f"{evidence_id}-label",
                    "s": person_iri,
                    "p": RDFS_LABEL,
                    "o": person,
                    "object_type": "literal",
                },
                {
                    "evidence_id": evidence_id,
                    "s": person_iri,
                    "p": LIVES_IN,
                    "o": city_iri,
                    "object_type": "iri",
                },
                {
                    "evidence_id": f"{evidence_id}-city-label",
                    "s": city_iri,
                    "p": RDFS_LABEL,
                    "o": city,
                    "object_type": "literal",
                },
            ],
            "entity_contexts": [
                {"entity": person_iri, "context": text},
                {"entity": city_iri, "context": city},
            ],
            "relevant_evidence_ids": [evidence_id],
        }
        events.append(validate_event(event))

    queries: list[dict[str, Any]] = []
    for index in range(10):
        target = index * 10
        language = "en" if index % 2 == 0 else "pt-BR"
        person = f"Person-{target:03d}"
        city = f"City-{target % 10:02d}"
        question = (
            f"Which city is {person} associated with?"
            if language == "en"
            else f"Com qual cidade {person} está associado?"
        )
        query = {
            "schema_version": "tg-query-v1",
            "query_id": f"tg0-query-{index:03d}",
            "namespace": "tg0-smoke",
            "language": language,
            "question": question,
            "query_type": "single-hop-paraphrase",
            "expected_answer": city,
            "relevant_evidence_ids": [f"tg0-evidence-{target:03d}"],
            "should_abstain": False,
        }
        queries.append(validate_query(query))

    workload = {
        "schema_version": "tg-workload-v1",
        "seed": seed,
        "events": events,
        "queries": queries,
    }
    workload["sha256"] = _fingerprint(workload)
    return workload
