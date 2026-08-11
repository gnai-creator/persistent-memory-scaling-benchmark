import copy

import pytest

from persistent_memory_scaling.trustgraph.contracts import ContractError, validate_event, validate_query
from persistent_memory_scaling.trustgraph.workload import generate_smoke_workload


def test_smoke_workload_is_frozen_and_deterministic():
    left = generate_smoke_workload()
    right = generate_smoke_workload()
    assert left == right
    assert len(left["events"]) == 100
    assert len(left["queries"]) == 10
    assert len(left["sha256"]) == 64


def test_event_contract_rejects_unknown_fields():
    event = copy.deepcopy(generate_smoke_workload()["events"][0])
    event["unknown"] = True
    with pytest.raises(ContractError, match="unexpected keys"):
        validate_event(event)


def test_query_contract_rejects_unknown_language():
    query = copy.deepcopy(generate_smoke_workload()["queries"][0])
    query["language"] = "xx"
    with pytest.raises(ContractError, match="language"):
        validate_query(query)


def test_event_ids_and_sequences_are_unique():
    events = generate_smoke_workload()["events"]
    assert len({event["event_id"] for event in events}) == 100
    assert [event["sequence"] for event in events] == list(range(100))
