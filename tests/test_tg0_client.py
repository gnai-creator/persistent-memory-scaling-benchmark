import sys
import types

from persistent_memory_scaling.trustgraph.client import TrustGraphClient


class FakeFlow:
    def __init__(self):
        self.started = []

    def list(self):
        return []

    def start(self, **kwargs):
        self.started.append(kwargs)


class FakeApi:
    latest = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.flow_client = FakeFlow()
        FakeApi.latest = self

    def flow(self):
        return self.flow_client


def test_start_flow_uses_public_api_and_frozen_parameters(monkeypatch):
    api_module = types.ModuleType("trustgraph.api")
    api_module.Api = FakeApi
    api_module.Triple = object
    knowledge_module = types.ModuleType("trustgraph.knowledge")
    knowledge_module.Uri = str
    knowledge_module.Literal = str
    monkeypatch.setitem(sys.modules, "trustgraph.api", api_module)
    monkeypatch.setitem(sys.modules, "trustgraph.knowledge", knowledge_module)

    client = TrustGraphClient("http://localhost:8888", "tg_test", flow_id="tg0")
    client.start_flow("qwen2.5:0.5b", "sentence-transformers/all-MiniLM-L6-v2")

    started = FakeApi.latest.flow_client.started
    assert len(started) == 1
    assert started[0]["blueprint_name"] == "everything"
    assert started[0]["parameters"]["llm-temperature"] == "0"
    assert started[0]["parameters"]["llm-model"] == "qwen2.5:0.5b"
