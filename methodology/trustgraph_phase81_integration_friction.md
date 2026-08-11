# TrustGraph Phase 8.1 integration observations

## Integration friction observed

During the paired Phase 8.1 integration, the TrustGraph SDK required compatibility
handling for the embeddings response shape, asynchronous indexing introduced
preparation latency, and vector-store writes required the collection to be
registered explicitly before ingestion. These issues were resolved externally in
the benchmark runner without modifying TrustGraph itself.

TrustGraph proved considerably more operationally complex to integrate than
expected. The paired benchmark required SDK compatibility handling, explicit
collection registration, asynchronous indexing waits, and careful separation of
setup, ingestion, indexing, query, and reader latency. Architectural capability
does not erase integration cost.

A system can be architecturally capable and still impose unnecessary operational
friction on the people trying to use it correctly.

The observations are operational integration findings, not retrieval-quality or
scaling results. They must not be added to query latency or reader latency.

## Timing boundaries

The paired runner records these phases separately:

1. **Setup / collection registration** — API client initialization, collection
   lookup, optional registration, and a short configuration-propagation guard.
2. **Ingestion submission** — submission of the entity-context batch to the
   TrustGraph bulk API. Because processing is asynchronous, this is not treated as
   completion of indexing.
3. **Indexing readiness** — elapsed time from successful submission until a
   sentinel memory from each of the 37 frozen bundles is recoverable from graph
   embeddings.
4. **Query** — only the graph-embeddings retrieval request for one frozen Phase 8.1
   question. The row-level `retrieval_latency_ms` field measures this phase.
5. **Reader** — only the shared Qwen3 14B answer-generation request after evidence
   selection. The row-level `reader_latency_ms` field measures this phase.

The benchmark therefore reports preparation cost as preparation cost and steady
query latency as query latency. It does not inflate retrieval latency with stack
startup, collection creation, ingestion, or indexing readiness.

## Final paired operational result and preliminary correction

At 395 of 979 completed questions, a progress estimate placed the TrustGraph path
approximately 18% behind before preparation and approximately 20% behind after
amortization. That projection did **not** hold in the completed run and must not be
reported as the final result.

Across all 979 questions, TrustGraph averaged 178.5 ms in retrieval and 1,235.6 ms
in the reader, or 1,414.1 ms combined. The completed ASM-CM + Memory Bridge 8.1
operational run averaged 1,294.1 ms per question from total wall time. TrustGraph
was therefore 9.3% slower before preparation. Amortizing 21.2 seconds of collection
setup, ingestion submission, and indexing readiness produced an effective mean of
1,435.8 ms, 10.9% above the ASM operational run.

TrustGraph combined latency was 1,382.8 ms at p50, 1,829.7 ms at p95, and 3,759.8
ms at maximum. Retrieval alone was 175.4 ms at p50, 265.0 ms at p95, and 356.4 ms
at maximum. Reader latency was 1,203.3 ms at p50, 1,652.1 ms at p95, and 3,635.2
ms at maximum.

## Compatibility handling

The installed SDK's `embeddings()` method returns an already-unwrapped vector list,
while its `graph_embeddings_query()` helper expects a response object containing a
second `vectors` field. The runner calls the same public `embeddings` and
`service/graph-embeddings` endpoints explicitly. No TrustGraph package or container
image is patched.

## Invalid preliminary run

Two preliminary full-corpus attempts were invalid and are excluded from all charts
and conclusions. The first used readiness of the first imported memory as its gate;
because indexing is asynchronous, questions began before the rest of the corpus was
searchable. The second searched one global 592-memory collection, while the frozen
Phase 8.1 protocol gives each question a closed 16-memory candidate bundle. The
corrected adapter uses one collection per bundle (37 collections) and requires a
sentinel from every bundle to be recoverable before question evaluation begins.
