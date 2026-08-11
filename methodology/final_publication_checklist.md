# Final publication checklist

This checklist closes the benchmark without treating a live checkpoint as a final result.

## Release gate

Run from the repository root:

```bash
PYTHONPATH=src python -m persistent_memory_scaling.finalization \
  --config configs/finalization.json \
  --json manifests/finalization-status.json \
  --markdown docs/report/013_finalization_status.md
```

Exit status `0` means every required artifact has the expected cardinality. Exit status `1`
means at least one run is partial, invalid, or absent. The command is read-only with respect to
the benchmark runs; it only writes the two requested status outputs.

## Protocol separation

The publication must contain three distinct result blocks. Results from these blocks must not be
combined into one leaderboard.

### MultiWOZ Phase 8.1 — 979 questions

- ASM-CM + Bridge 8.1;
- ASM-CM + Bridge 8.1 + Vector + BM25 hybrid;
- TrustGraph graph-embeddings retrieval;
- TrustGraph Full GraphRAG;
- Vector RAG and BM25 controls.

Report Recall@5, diagnostic answer score, reader input tokens, retrieval latency, reader latency,
and end-to-end latency where the run measured them. Full GraphRAG must remain a separate bar from
graph-embeddings retrieval.

### Free-language retrieval — 128 questions

- all completed R3.2 systems;
- TrustGraph graph-embeddings retrieval on the exact same 128 question IDs;
- TrustGraph Full GraphRAG on the exact same 128 question IDs.

Report Recall@5, diagnostic answer score, reader input tokens, retrieval latency, and end-to-end
latency. The R3.2 result is negative/non-promoted and must be published as such.

### LongMemEval-S + GPT-4o — 500 questions

- ASM-CM + Bridge;
- Vector and BM25;
- completed RRF hybrid systems;
- TrustGraph graph-embeddings retrieval with the same external GPT-4o reader;
- TrustGraph Full GraphRAG configured with GPT-4o.

Report Recall@15, official GPT-4o judge accuracy, reader input tokens, retrieval latency, reader
latency, total latency, and provenance observability. Keep the official judge metric visually and
textually separate from the diagnostic answer score. This is an external-generalization protocol,
not a direct replication of another vendor's published benchmark.

## Chart rules

- English text only.
- Matplotlib output in both PNG and SVG.
- Put `n` and the protocol name in every figure.
- Do not draw bars for unavailable metrics; label them `not measured` in notes or tables.
- Do not convert missing Full GraphRAG provenance into a zero Recall value.
- Label partial/smoke results and never place them beside completed runs as if equivalent.
- Separate reader-only latency from retrieval and end-to-end latency.
- State runtime differences when reader timings were collected under different conditions.
- Keep measured values solid and projections dotted; never extrapolate ASM scaling from c100.
- Distinguish peak container RAM from 30-second mean container RAM.

## Numerical audit

Before editing either article:

1. Verify question IDs and counts, not only row counts.
2. Verify the reader, prompt, evaluator, top-k, and context policy for each paired comparison.
3. Recompute aggregates from rows and compare them with stored summaries.
4. Compute p50 and p95 from per-question latency rows where available.
5. Record failures, retries, timeouts, indexing waits, and preparation time separately.
6. Record SHA-256 hashes of promoted input and result artifacts.
7. Preserve negative and non-promoted ASM results.
8. Mark the 1M TrustGraph storage point as projected, not measured.

## Editorial closure

Only after the release gate is green:

1. regenerate the three protocol-specific charts;
2. update `article.md` with final values and limitations;
3. update `linkedin_article.md` with a compact subset of the same defensible claims;
4. replace public URL placeholders;
5. verify the current GitHub star count immediately before publication, or remove it from the title;
6. run the full test suite and inspect `git diff --check`;
7. publish the repository only after secrets and machine-local paths have been audited.

Horizontal multi-instance scaling remains future work. It is not required to close this benchmark
and must not be presented as measured here.
