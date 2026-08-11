from persistent_memory_scaling.longmemeval_consumption_accuracy_plot import measurements


def test_measurements_merge_asm_and_trustgraph() -> None:
    asm = {
        "summary": {key: {"reader_input_tokens_mean": 1000} for key in (
            "asm_bridge81_gpt4o", "vector_bridge81_gpt4o", "bm25_bridge81_gpt4o",
            "asm_vector_rrf_bridge81_gpt4o", "asm_bm25_rrf_bridge81_gpt4o",
            "vector_bm25_rrf_bridge81_gpt4o", "asm_vector_bm25_rrf_bridge81_gpt4o",
        )},
        "official_evaluation": {"results": {key: {"accuracy": .5} for key in (
            "asm_bridge81_gpt4o", "vector_bridge81_gpt4o", "bm25_bridge81_gpt4o",
            "asm_vector_rrf_bridge81_gpt4o", "asm_bm25_rrf_bridge81_gpt4o",
            "vector_bm25_rrf_bridge81_gpt4o", "asm_vector_bm25_rrf_bridge81_gpt4o",
        )}},
    }
    trustgraph = {
        "summary": {"reader_input_tokens_mean": 2000},
        "official_evaluation": {"results": {
            "trustgraph_graph_embeddings_gpt4o": {"accuracy": .7}
        }},
    }
    result = measurements(asm, trustgraph)
    assert result["asm_bridge81_gpt4o"] == {"tokens": 1000.0, "accuracy": 50.0}
    assert result["trustgraph_graph_embeddings_gpt4o"] == {"tokens": 2000.0, "accuracy": 70.0}
