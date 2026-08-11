# Final benchmark release gate

Overall status: **NOT READY**

This report is generated from artifacts only. It does not start, stop, or modify benchmark processes.

## MultiWOZ Phase 8.1 — 979 questions

Protocol status: **NOT READY**

| Artifact | Status | Evidence |
|---|---:|---|
| `asm_phase81_baseline` | ready | complete=True; examples=979/979 |
| `asm_phase81_hybrid` | ready | 979/979 rows for asm_vector_bm25_compact |
| `trustgraph_graph_embeddings` | ready | 979/979 questions |
| `trustgraph_full_graphrag` | incomplete | 10/979 questions |

## Free-language retrieval — 128 questions

Protocol status: **NOT READY**

| Artifact | Status | Evidence |
|---|---:|---|
| `asm_r32` | ready | complete=True; examples=128/128 |
| `trustgraph_graph_embeddings` | missing | file does not exist |
| `trustgraph_full_graphrag` | missing | file does not exist |

## LongMemEval-S + GPT-4o — 500 questions

Protocol status: **NOT READY**

| Artifact | Status | Evidence |
|---|---:|---|
| `asm_bridge81_gpt4o` | ready | complete=True; examples=500/500 |
| `asm_hybrids_gpt4o` | running | vector_bridge81_gpt4o=377/500, bm25_bridge81_gpt4o=377/500, asm_vector_rrf_bridge81_gpt4o=377/500, asm_bm25_rrf_bridge81_gpt4o=377/500, vector_bm25_rrf_bridge81_gpt4o=377/500, asm_vector_bm25_rrf_bridge81_gpt4o=377/500 |
| `trustgraph_graph_embeddings_gpt4o` | missing | file does not exist |
| `trustgraph_full_graphrag_gpt4o` | missing | file does not exist |
