"""Frozen MultiWOZ workload with deterministic, cumulative in-domain distractors."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Document:
    memory_id: str
    content: str
    source_id: str


@dataclass(frozen=True)
class QuerySpec:
    query_id: str
    question: str
    expected_answer: str
    relevant_memory_ids: tuple[str, ...]


@dataclass(frozen=True)
class Workload:
    base_documents: tuple[Document, ...]
    distractors: tuple[Document, ...]
    queries: tuple[QuerySpec, ...]
    evaluation_ids: tuple[str, ...]
    dataset_sha256: str


def parse_distractor_checkpoints(value: str) -> list[int]:
    try:
        points = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise ValueError("distractor checkpoints must be comma-separated integers") from exc
    if not points or any(point < 0 for point in points):
        raise ValueError("distractor checkpoints must be non-negative")
    if points != sorted(set(points)):
        raise ValueError("distractor checkpoints must be unique and increasing")
    return points


def _document(memory: Any) -> Document:
    return Document(
        memory_id=str(memory.memory_id),
        content=str(memory.content),
        source_id=str(memory.source_id),
    )


def _unique_documents(instances: list[Any]) -> list[Document]:
    values: dict[str, Document] = {}
    for instance in instances:
        for memory in instance.memories:
            values.setdefault(str(memory.memory_id), _document(memory))
    return list(values.values())


def load_workload(
    multiwoz_root: Path,
    phase8_results: Path,
    *,
    query_count: int,
    distractor_count: int,
) -> Workload:
    """Load the frozen supported Phase-8 questions and held-out train distractors."""
    if query_count < 1 or distractor_count < 0:
        raise ValueError("query_count must be positive and distractor_count non-negative")
    from benchmarks.multiwoz.adapter import load_multiwoz

    phase8 = json.loads(phase8_results.read_text(encoding="utf-8"))
    protocol = phase8["protocol"]
    evaluation_ids = tuple(str(item) for item in protocol["evaluation_question_ids"][:query_count])
    if len(evaluation_ids) != query_count:
        raise ValueError("requested more questions than the frozen MultiWOZ evaluation cohort")
    all_test = load_multiwoz(
        multiwoz_root,
        "test",
        bundle_size=16,
        maximum=int(protocol["source_evaluation_examples"]),
    )
    by_id = {str(instance.question_id): instance for instance in all_test}
    missing = set(evaluation_ids) - set(by_id)
    if missing:
        raise ValueError(f"frozen MultiWOZ questions are missing: {sorted(missing)[:3]}")
    selected = [by_id[item] for item in evaluation_ids]
    base_documents = _unique_documents(selected)
    base_ids = {item.memory_id for item in base_documents}

    # Training dialogues are in-domain but disjoint from the frozen test questions.
    # Loading all generated task instances is deterministic; document IDs are then
    # de-duplicated in corpus order so every checkpoint is a prefix of one stream.
    train_instances = load_multiwoz(multiwoz_root, "train", bundle_size=16)
    distractors = [item for item in _unique_documents(train_instances) if item.memory_id not in base_ids]
    if distractor_count > len(distractors):
        raise ValueError(
            f"requested {distractor_count} distractors, but MultiWOZ train provides "
            f"only {len(distractors)} unique dialogue documents"
        )
    queries = tuple(
        QuerySpec(
            query_id=str(instance.question_id),
            question=str(instance.question),
            expected_answer=str(instance.answer),
            relevant_memory_ids=tuple(str(item) for item in instance.answer_memory_ids),
        )
        for instance in selected
    )
    return Workload(
        base_documents=tuple(base_documents),
        distractors=tuple(distractors[:distractor_count]),
        queries=queries,
        evaluation_ids=evaluation_ids,
        dataset_sha256=str(protocol["dataset_sha256"]),
    )


def workload_sha256(workload: Workload) -> str:
    payload = {
        "base": [(item.memory_id, item.content, item.source_id) for item in workload.base_documents],
        "distractors": [
            (item.memory_id, item.content, item.source_id) for item in workload.distractors
        ],
        "queries": [
            (item.query_id, item.question, item.expected_answer, item.relevant_memory_ids)
            for item in workload.queries
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
