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

## Full GraphRAG friction behind a Recall@5 comparison

Producing a defensible Recall@5 value from Full GraphRAG is not a single endpoint
call. Full GraphRAG is an end-to-end pipeline: it grounds entities, explores graph
edges, filters or reranks the resulting subgraph, builds a synthesis prompt and
returns a generated answer. Its public result is therefore not inherently the
ranked list of five frozen memory IDs required by Recall@5.

The Full GraphRAG extension to this benchmark consequently requires all of the
following before a Recall@5 value can be published:

1. create an explicit graph representation for every frozen MultiWOZ memory;
2. preserve a stable URI that maps each graph entity back to its benchmark
   `memory_id`;
3. register an isolated collection for each frozen 16-memory candidate bundle;
4. submit both graph triples and entity contexts;
5. wait independently for graph-store and embedding readiness;
6. execute the complete grounding, exploration, focus/reranking and synthesis
   path;
7. map returned provenance sources back to frozen memory IDs; and
8. report Recall@5 only when that mapping is complete and unambiguous.

If Full GraphRAG returns a valid answer but does not expose five mappable memory
sources, answer quality remains measurable while Recall@5 is **not available**.
The benchmark will not convert a missing ranked-ID interface into a zero, infer a
ranking from generated prose, or reuse the graph-embeddings Recall@5 value.

Operationally, the clean Full GraphRAG run also requires IAM bootstrap before the
gateway can authenticate requests, backend convergence before the default flow is
usable, explicit collection registration and asynchronous indexing barriers. This
is material integration work for obtaining what appears in the final chart as one
retrieval metric.

The first authenticated Full GraphRAG flow was configured with
`nomic-embed-text`, matching the embedding model used elsewhere in the paired
Phase 8 protocol. Flow creation accepted the parameter, but the request later
failed inside TrustGraph because its `TextEmbedding` implementation did not
support that model. The invalid attempt is excluded. The corrected Full GraphRAG
flow uses the deployment-supported
`sentence-transformers/all-MiniLM-L6-v2`; the synthesis model remains Qwen3 14B.

### Harness errors excluded from the TrustGraph finding

The first isolated Full GraphRAG deployment was started without an IAM bootstrap
token and could not initialize IAM. A subsequent temporary token omitted the
required `tg_` prefix: IAM accepted it during seeding, but the gateway rejected it.
Both attempts are benchmark-harness configuration errors. They are recorded for
reproducibility, excluded from measurements, and are not attributed to TrustGraph
retrieval quality or latency.

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
## Full GraphRAG runtime reliability

A full 979-question Full GraphRAG execution also exposed a runtime reliability issue.
After the 10-question smoke completed, the resumed run failed on its first new question
with HTTP 504 from `service/graph-rag`; the process exited after approximately 5 minutes
34 seconds of wall time and retained the 10 completed rows. The benchmark runner was
then changed to checkpoint each completed question, resume without replacing completed
answers, and retry GraphRAG and official explainability calls with bounded exponential
backoff. Retries and their elapsed time remain part of the observed operational path and
are recorded per question; they are not silently removed from latency accounting.

Subsequent inspection found that this failed run overlapped a separate Qwen3 reader
workload and ASM training. At diagnosis time the GPU reported 99% utilization and
21,994 MiB of 24,564 MiB allocated. TrustGraph timed out while `extract_concepts`
waited for `text-completion`; the public gateway returned 504 before the internal
GraphRAG request reached its own timeout. Early retries could therefore overlap an
older still-running backend request. These contention-affected attempts are retained
as an operational diagnostic but will not be presented as an isolated TrustGraph
reliability rate or clean latency measurement. The corrected runner avoids reimporting
on resume and waits long enough that timed-out internal calls cannot overlap retries.

## Observed concurrency on the benchmark host

During this work, the same host sustained two simultaneous local Ollama instances,
including a Qwen3 14B reader, alongside two ASM-CM processes, while another ASM-CM
workload used an external GPT-4o reader. The external reader does not consume local model
VRAM, so this observation must not be interpreted as an equivalent additional local
inference workload. It nevertheless shows that two local Ollama servers and multiple
ASM-CM processes coexisted on this machine.

Under the concurrently loaded configuration tested here, the TrustGraph Full GraphRAG
path did not make forward progress: its internal concept-extraction LLM requests timed
out while the GPU was at 99% utilization and 21,994 of 24,564 MiB was allocated. This
supports a host-specific operational conclusion: the measured TrustGraph deployment
could not be added successfully to that already active workload without serializing or
reallocating resources.

This is not yet a controlled concurrency benchmark and does not establish that
TrustGraph can never support the same concurrency on different hardware, with a remote
LLM, or under another deployment configuration. A direct claim requires matched reader
placement, request rate, model residency, GPU allocation and success criteria.

## Dedicated endpoint and unbounded orphaned generation

The next isolated Full GraphRAG attempt initially failed because TrustGraph's
`text-completion-rag` container expected a dedicated Ollama endpoint at
`172.19.0.1:11435`, while only a loopback-bound service existed at
`127.0.0.1:11434`. GraphRAG surfaced `LLM returned no response`; the container log
contained the underlying connection refusal.

After the dedicated endpoint was restored, the gateway returned HTTP 504 while the
Ollama backend continued generating after the client request had expired. One orphaned
generation exceeded 25,000 decoded tokens. A client retry could consequently overlap
unfinished backend work and invalidate latency measurements.

The original 10-question smoke artifact is preserved and is not mixed with the
corrected full run. The corrected protocol uses a separate Ollama model alias with
`/no_think` and frozen `num_predict=1024`, together with a new TrustGraph flow,
collection prefix, and output artifact. This is a benchmark-side deployment constraint;
TrustGraph source code remains unmodified. The output limit and failed attempts must be
disclosed with the final Full GraphRAG result.

A one-question validation of the bounded configuration completed without retry or
gateway timeout. Full GraphRAG took 17.38 seconds and the separate explainability
replay took 8.44 seconds. Across its internal calls it reported 257 input tokens and
1,127 output tokens. The question received 0 diagnostic answer score but grounding
Recall@5 was successful; this smoke validates runtime completion, not quality.

## Methodological disposition of the failed run

The failing execution is not resumed into the corrected result. Although ten rows from
the earlier smoke remain preserved for audit, the official bounded execution starts at
0/979 in a new `v2` artifact. Combining those rows would mix different model-output
bounds, flow identities, collection namespaces, timeout behavior, and retry semantics.

The observed sequence was:

1. the dedicated TrustGraph Ollama endpoint was unavailable, producing a generic public
   `LLM returned no response` error backed by a container-level connection refusal;
2. after endpoint restoration, the first question returned HTTP 504;
3. the Ollama backend continued the abandoned generation beyond 25,000 decoded tokens;
4. the configured 330-second retry could overlap that unfinished generation;
5. the run was stopped because its latency and retry measurements were no longer clean;
6. a bounded model alias, new flow, new collection namespace, and new artifact were
   introduced before validation and the full restart.

This is reported as integration and runtime-reliability evidence, not as a final
TrustGraph quality result. It also explains why simply increasing the retry delay was
not an adequate correction: the client timeout did not cancel the backend computation.
No TrustGraph source code or container image was modified, and no ASM-CM process or its
Ollama service was stopped or reconfigured during this correction.

## Isolated reproduction of the query-11 JSON failure

The bounded run completed ten questions and then failed while processing
`multiwoz:test:PMUL0815.json:train:train-leaveat` with:

```text
graph-rag-error: the JSON object must be str, bytes or bytearray, not NoneType
```

To distinguish an input-dependent failure from accumulated runtime state, the same
question was executed alone against the same bounded flow and the same already indexed
canonical collection. The diagnostic used two attempts with a two-second backoff rather
than the official 330-second delay; it wrote to a separate diagnostic target and did not
modify the ten-row benchmark checkpoint. Both isolated attempts returned the identical
`NoneType` JSON parsing error.

This reproduction weighs against the hypothesis that the failure was caused merely by
being the eleventh sequential request. Under the tested configuration it is a
deterministic, input-dependent Full GraphRAG pipeline failure (2/2 isolated attempts).
The public exception identifies a missing intermediate JSON value but does not expose
which internal pipeline stage produced `None`; this benchmark therefore does not claim
a deeper root cause without additional service-level evidence.

The run was stopped at 10/979 rather than configured to skip the failing question.
Silently skipping it would change the frozen question set and overstate completion and
reliability. The ten successful answers remain a diagnostic sample, while the failed
question is reported as an observed execution failure rather than assigned a fabricated
answer or retrieval score.

## LongMemEval collection-registration timeout

The first TrustGraph graph-embeddings attempt on LongMemEval-S failed before ingestion or
GPT-4o evaluation. The paired isolation protocol requires one collection per frozen
candidate bundle, which produces 500 collections for this corpus. The runner registered
119 collections rapidly and then the request for collection 120 remained outstanding for
600 seconds. The API gateway returned HTTP 504 to the client. Gateway and control-service
logs showed that collections 1–119 were persisted successfully; the collection-120
request did not reach the librarian handler during the timeout window. Cassandra,
Qdrant, Pulsar, the API gateway, and the TrustGraph control container remained running.

The runner was changed externally to make this administrative phase resumable and
observable. It now lists and skips already persisted collections, uses a separate
30-second administrative client for each attempt, recreates that client after failure,
allows four bounded attempts with a two-second delay, introduces 50 ms of pacing between
registrations, and logs every collection and attempt. No TrustGraph package, image, or
service configuration was patched.

On restart, the 119 existing collections were reused. The runner passed collection 120
and reached at least collection 175, all on the first corrected attempt. This supports a
burst/request-path setup failure rather than a bad LongMemEval record. The incident is
reported as integration friction and setup reliability; it is not included in retrieval
latency or GPT-4o reader latency.
