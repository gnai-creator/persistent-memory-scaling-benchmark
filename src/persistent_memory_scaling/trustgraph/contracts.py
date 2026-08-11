"""Dependency-free validation for the frozen TG-0 contracts.

The JSON Schema files are the publication format. These validators deliberately
cover the same required invariants without making workload generation depend on
an external schema library.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class ContractError(ValueError):
    """Raised when a benchmark record violates a frozen contract."""


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{path} must be an object")
    return value


def _sequence(value: Any, path: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ContractError(f"{path} must be an array")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{path} must be a non-empty string")
    return value


def _exact_keys(record: Mapping[str, Any], required: set[str], path: str) -> None:
    missing = required - set(record)
    extra = set(record) - required
    if missing:
        raise ContractError(f"{path} missing keys: {sorted(missing)}")
    if extra:
        raise ContractError(f"{path} unexpected keys: {sorted(extra)}")


def validate_event(value: Any) -> dict[str, Any]:
    event = dict(_mapping(value, "event"))
    required = {
        "schema_version", "event_id", "sequence", "namespace", "language",
        "text", "triples", "entity_contexts", "relevant_evidence_ids",
    }
    _exact_keys(event, required, "event")
    if event["schema_version"] != "tg-event-v1":
        raise ContractError("event.schema_version must be tg-event-v1")
    _string(event["event_id"], "event.event_id")
    _string(event["namespace"], "event.namespace")
    if event["language"] not in {"en", "pt-BR"}:
        raise ContractError("event.language must be en or pt-BR")
    _string(event["text"], "event.text")
    if not isinstance(event["sequence"], int) or event["sequence"] < 0:
        raise ContractError("event.sequence must be a non-negative integer")
    triples = _sequence(event["triples"], "event.triples")
    if not triples:
        raise ContractError("event.triples must not be empty")
    for index, item in enumerate(triples):
        triple = _mapping(item, f"event.triples[{index}]")
        _exact_keys(triple, {"evidence_id", "s", "p", "o", "object_type"}, f"event.triples[{index}]")
        for key in ("evidence_id", "s", "p", "o"):
            _string(triple[key], f"event.triples[{index}].{key}")
        if triple["object_type"] not in {"iri", "literal"}:
            raise ContractError(f"event.triples[{index}].object_type is invalid")
    contexts = _sequence(event["entity_contexts"], "event.entity_contexts")
    for index, item in enumerate(contexts):
        context = _mapping(item, f"event.entity_contexts[{index}]")
        _exact_keys(context, {"entity", "context"}, f"event.entity_contexts[{index}]")
        _string(context["entity"], f"event.entity_contexts[{index}].entity")
        _string(context["context"], f"event.entity_contexts[{index}].context")
    evidence = _sequence(event["relevant_evidence_ids"], "event.relevant_evidence_ids")
    for index, item in enumerate(evidence):
        _string(item, f"event.relevant_evidence_ids[{index}]")
    return event


def validate_query(value: Any) -> dict[str, Any]:
    query = dict(_mapping(value, "query"))
    required = {
        "schema_version", "query_id", "namespace", "language", "question",
        "query_type", "expected_answer", "relevant_evidence_ids", "should_abstain",
    }
    _exact_keys(query, required, "query")
    if query["schema_version"] != "tg-query-v1":
        raise ContractError("query.schema_version must be tg-query-v1")
    for key in ("query_id", "namespace", "question", "query_type"):
        _string(query[key], f"query.{key}")
    if query["language"] not in {"en", "pt-BR"}:
        raise ContractError("query.language must be en or pt-BR")
    if not isinstance(query["expected_answer"], str):
        raise ContractError("query.expected_answer must be a string")
    if not isinstance(query["should_abstain"], bool):
        raise ContractError("query.should_abstain must be boolean")
    _sequence(query["relevant_evidence_ids"], "query.relevant_evidence_ids")
    return query


def validate_manifest(value: Any) -> dict[str, Any]:
    manifest = dict(_mapping(value, "manifest"))
    required = {
        "schema_version", "run_id", "created_at", "phase", "status", "seed",
        "event_count", "query_count", "workspace", "collection", "flow_id",
        "upstream", "deployment", "models", "hardware", "artifacts",
    }
    _exact_keys(manifest, required, "manifest")
    if manifest["schema_version"] != "tg-run-manifest-v1":
        raise ContractError("manifest.schema_version must be tg-run-manifest-v1")
    for key in ("run_id", "created_at", "phase", "status", "workspace", "collection", "flow_id"):
        _string(manifest[key], f"manifest.{key}")
    for key in ("seed", "event_count", "query_count"):
        if not isinstance(manifest[key], int) or manifest[key] < 0:
            raise ContractError(f"manifest.{key} must be a non-negative integer")
    for key in ("upstream", "deployment", "models", "hardware", "artifacts"):
        _mapping(manifest[key], f"manifest.{key}")
    return manifest
