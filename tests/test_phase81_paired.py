from persistent_memory_scaling.trustgraph.phase81_paired import (
    decode_matches,
    entity_uri,
    graph_embeddings_query,
)


def test_entity_uri_is_stable_and_decode_preserves_score():
    uri = entity_uri("memory:one")
    assert uri == entity_uri("memory:one")
    assert uri != entity_uri("memory:two")
    assert decode_matches({"entities": [{"entity": {"t": "i", "i": uri}, "score": .75}]},
                          {uri: "memory:one"}) == [("memory:one", .75)]


def test_graph_embeddings_query_uses_unwrapped_vectors():
    class Flow:
        def embeddings(self, texts):
            assert texts == ["query"]
            return [[0.1, 0.2]]

        def request(self, service, payload):
            assert service == "service/graph-embeddings"
            assert payload == {"vector": [0.1, 0.2], "collection": "c", "limit": 5}
            return {"entities": []}

    assert graph_embeddings_query(Flow(), "query", "c", 5) == {"entities": []}
