# Persistent Memory Scaling Benchmark

A reproducible benchmark for comparing persistent memory architectures for AI agents as history grows.

The initial comparison focuses on two substantially different approaches:

- **TrustGraph** — persistent memory represented through graph-oriented storage, structured knowledge, provenance and retrieval infrastructure.
- **ASM-CM — Aletheion Compact Memory Model** — persistent associative memory designed around a bounded retained state rather than a history-sized active representation.

This repository does **not** assume that one architecture is universally better than the other.

It asks a narrower and measurable question:

> What happens to memory cost, retrieval quality and latency as an AI agent's history grows?

---

## Motivation

Persistent memory is increasingly treated as a requirement for long-running AI agents.

However, the term **memory** is used for architectures with very different computational properties.

A system may remember by:

- storing past events explicitly;
- building a knowledge graph;
- storing entities and relationships;
- maintaining document or graph embeddings;
- retrieving historical records from a database;
- maintaining recurrent state;
- compressing historical associations into a bounded latent representation;
- or combining several of these approaches.

These systems can all legitimately be described as providing memory, while having very different scaling behavior.

That distinction matters.

An architecture capable of retrieving the correct event after one million interactions may nevertheless require storage proportional to those one million interactions.

Another architecture may maintain a small persistent state independent of history length, but sacrifice exact reconstruction, provenance or retrieval accuracy.

Therefore, comparing memory systems only by asking:

> "Does it remember?"

is insufficient.

A more useful question is:

> **How does it remember, what resources grow with history, and what capabilities are preserved as a consequence?**

This benchmark was created to investigate that question experimentally.

---

## Why TrustGraph and ASM-CM?

TrustGraph and ASM-CM represent two particularly different approaches to persistent AI memory.

### TrustGraph

TrustGraph uses structured storage and graph-oriented representations for knowledge and memory.

Its public repository contains infrastructure for persistent graph and knowledge storage, including Cassandra-backed components, as well as vector-storage paths for document and graph embeddings.

The project also supports vector-store implementations such as Qdrant, Pinecone and Milvus.

In other words, TrustGraph preserves historical knowledge through explicit persistent structures that can later be queried and reconstructed.

That provides important properties such as:

- explicit relationships;
- provenance;
- structured retrieval;
- inspectability;
- exact historical records;
- graph traversal;
- semantic search.

The expected architectural consequence is that persistent storage grows as additional knowledge is represented.

This benchmark will measure that behavior rather than assume its magnitude.

### ASM-CM

ASM-CM investigates a different architecture.

Instead of treating every historical event as part of an expanding active memory structure, ASM-CM maintains a compact associative state that is updated as events arrive.

The central property being tested is:

> History may continue growing while the retained associative state remains bounded.

Previous ASM-CM experiments measured a retained state of approximately **140 KiB per stream** under the tested configuration.

That number must not be interpreted as lossless storage of an arbitrary history.

ASM-CM does not claim that 140 KiB can contain every original document verbatim.

Exact source material, when required, must be accounted for separately.

The benchmark therefore distinguishes:

1. **associative state**
2. **canonical historical payload storage**
3. **active inference memory**
4. **retrieved context delivered to the language model**

This distinction is essential for a fair comparison.

---

# Research question

The primary question is:

> **How do persistent AI memory architectures scale as the amount of historical information increases?**

The benchmark will examine histories ranging from small conversational streams to workloads containing hundreds of thousands or potentially millions of events.

The objective is not merely to measure whether a system can retrieve information.

We want to measure simultaneously:

- how much it remembers;
- how accurately it remembers;
- how much it stores;
- how much memory it keeps resident;
- how much context it must reconstruct;
- how long retrieval takes;
- and how those quantities change as history grows.

---

# Core hypothesis

The benchmark begins with the following falsifiable hypothesis:

> Explicit graph and retrieval-based memory systems will require increasing persistent storage as represented history grows, while ASM-CM's retained associative state can remain approximately bounded with respect to history length.

This hypothesis does **not** imply that ASM-CM will outperform graph memory in retrieval quality.

Several outcomes are possible.

For example:

- TrustGraph may require more storage but achieve substantially better exact retrieval.
- ASM-CM may maintain much smaller retained state but lose information as history becomes dense.
- TrustGraph may provide stronger provenance and temporal reasoning.
- ASM-CM may offer lower per-agent persistent-state cost.
- One architecture may dominate for short histories and another for extremely long histories.
- A hybrid architecture may ultimately be preferable to either system individually.

All such outcomes are valid experimental results.

---

# What this benchmark will measure

The benchmark separates resource usage into several categories instead of reporting one ambiguous "memory usage" number.

## 1. Persistent storage

Total durable storage required after ingestion.

Examples include:

### TrustGraph

Where applicable:

- graph records;
- triples;
- reified statements;
- entities;
- relationships;
- metadata;
- provenance;
- Cassandra storage;
- document embeddings;
- graph embeddings;
- vector-store indexes.

### ASM-CM

Reported separately:

- ASM-CM retained state;
- state snapshots;
- optional external payload storage.

The benchmark will never combine ASM-CM's bounded state with external payload storage and then describe the result as "140 KiB total storage."

Likewise, TrustGraph's persistent database size will not be confused with its active RAM usage.

---

## 2. Resident RAM

Resident memory consumed while the system is running.

Measurements may include:

- process RSS;
- database memory where measurable;
- vector-store resident memory;
- caches;
- retrieval workers;
- ASM-CM runtime state.

Because database systems may deliberately cache disk-backed data in RAM, persistent storage and resident RAM will always be reported independently.

---

## 3. GPU memory

Where GPU execution is involved, the benchmark will record:

- baseline VRAM;
- peak VRAM during ingestion;
- peak VRAM during retrieval;
- peak VRAM during reader inference.

The memory layer and the language model will be reported separately whenever practical.

---

## 4. Retained state per agent

One of the most important measurements.

For each architecture we will estimate or directly measure:

```text
bytes retained per agent
```

at different history sizes.

For example:

```text
1,000 events
10,000 events
100,000 events
1,000,000 events
```

This produces a memory scaling curve rather than a single benchmark point.

---

## 5. Persistent bytes per event

For systems whose storage grows with history:

```text
additional persistent bytes
---------------------------
additional ingested events
```

will be measured.

This provides an empirical storage-growth coefficient.

---

## 6. Write latency

For each event:

- median ingestion latency;
- p95 latency;
- p99 latency;
- throughput in events/second.

The benchmark will also test whether ingestion becomes slower as the existing memory grows.

---

## 7. Query latency

Queries will be executed after progressively larger histories.

Measurements include:

- median retrieval latency;
- p95;
- p99;
- query throughput.

A memory system that remains accurate but becomes progressively slower with accumulated history exhibits a different scaling regime from one whose retrieval cost remains stable.

---

## 8. Retrieval accuracy

Resource efficiency alone is meaningless if the memory cannot retrieve the correct information.

The benchmark will therefore measure:

- Recall@1;
- Recall@5;
- Recall@10;
- Mean Reciprocal Rank;
- false retrieval rate;
- abstention accuracy where supported.

Retrieval is evaluated independently from the language model reader.

---

## 9. End-to-end answer quality

A common reader LLM will receive the evidence produced by each system.

The same:

- model;
- generation settings;
- prompts;
- evidence budget;
- evaluation questions

must be used wherever possible.

Metrics may include:

- exact match;
- token F1;
- benchmark-specific QA scores;
- unsupported-answer rate;
- citation correctness.

This separates:

```text
memory retrieval failure
```

from:

```text
reader reasoning failure
```

---

## 10. Context delivered to the LLM

A memory system may store a large amount of history while retrieving only a small subset for each query.

Therefore the benchmark will separately measure:

- retrieved bytes;
- retrieved tokens;
- number of memories returned;
- reader prompt size.

This lets us distinguish:

> total persistent history

from:

> active context required for the current inference.

---

# Scaling workloads

The initial target sequence is:

| Stage | Historical events |
|------:|------------------:|
| S1 | 1,000 |
| S2 | 10,000 |
| S3 | 100,000 |
| S4 | 1,000,000 |

Smaller intermediate stages may be added for plotting crossover behavior.

Every system receives the same ordered event stream.

Measurements are taken after each stage.

The resulting plots should make it possible to inspect whether a metric behaves approximately as:

```text
O(1)
O(log N)
O(N)
```

or follows some other empirical scaling regime.

No asymptotic complexity claim will be made solely from a few experimental points.

---

# Benchmark dimensions

The initial benchmark will produce at least the following curves.

## History size vs persistent storage

```text
events → bytes stored
```

## History size vs resident RAM

```text
events → RSS / working-set memory
```

For ASM-CM, this curve will be decomposed into logical associative-state bytes,
idle process RSS, ingestion peak and query peak. A flat logical state is not
inferred from `docker stats` alone.

## History size vs retained per-agent state

```text
events → per-agent state bytes
```

## History size vs write latency

```text
events → ingestion latency
```

## History size vs query latency

```text
events → retrieval latency
```

## History size vs retrieval quality

```text
events → Recall@K
```

## History size vs reader context

```text
events → tokens delivered to LLM
```

This is reported as a distribution, not only as a mean:

```text
events → reader-context tokens at p50 / p95 / p99
```

The context curve is always shown beside Recall@5 and answer-quality curves.
A lower context percentile is an efficiency result only at matched or improved
quality. The executable observation contract, quality gate, paired 10k/100k/1M
protocol and graph generator are specified in
[methodology/reader_context_distribution.md](methodology/reader_context_distribution.md).

Together these curves describe a memory system much more completely than a single accuracy score.

---

# Exact memory vs associative memory

A central methodological distinction in this benchmark is the difference between:

### Exact historical storage

A system preserves enough information to reconstruct original records, facts or relationships.

and:

### Associative state

A system preserves an internal representation that helps identify or reconstruct relevant information without necessarily retaining the original payload itself.

Neither is automatically superior.

Exact storage provides:

- auditability;
- provenance;
- deterministic recovery;
- deletion semantics;
- explicit temporal records.

Associative state may provide:

- compactness;
- constant-sized active state;
- cheap per-agent continuity;
- reduced active context;
- efficient long-running state.

The benchmark exists in part to quantify this trade-off.

---

# Fair accounting

Several accounting rules are mandatory.

### Rule 1 — Disk is not RAM

Disk-backed databases cannot be described as consuming their entire database size in active RAM.

### Rule 2 — Retrieval context is not total storage

A system that stores 10 GB but retrieves 2 KB for a query uses 2 KB of retrieved context, not 10 GB.

Both numbers must be reported.

### Rule 3 — ASM-CM state is not lossless historical storage

A bounded neural state cannot be compared directly with a graph database while pretending that it provides identical reconstruction guarantees.

### Rule 4 — External payloads count

If ASM-CM requires an external payload store for an experiment, its size will be reported separately and included in any total-storage comparison where appropriate.

### Rule 5 — Indexes count

Graph indexes, vector indexes and auxiliary database structures count toward persistent storage.

### Rule 6 — Shared infrastructure must be separated from per-agent cost

For multi-agent experiments:

```text
shared model/runtime cost
```

and

```text
incremental cost per agent
```

will be reported independently.

### Rule 7 — Bounded working memory does not mean bounded total storage

ASM-CM may retain a bounded associative working state while its canonical
payload archive and auxiliary indexes grow on disk. Both are valid costs, but
they answer different questions and will be plotted separately.

### Rule 8 — RSS alone cannot establish bounded state

Runtime overhead, allocators, caches and temporary buffers can move RSS without
changing the logical associative state. The benchmark will report baseline,
stabilized idle RAM, ingestion peak, query peak, post-query RAM and logical
state size independently.

---

# Multi-agent scaling

Persistent AI systems are especially interesting when thousands of agents require independent memories.

Future stages will therefore measure:

```text
1 agent
10 agents
100 agents
1,000 agents
10,000 agents
```

where hardware permits.

The key metric will be:

> incremental memory cost per additional independent history.

This avoids confusing the shared cost of an LLM or database server with the memory required by each agent.

---

# TrustGraph storage paths

The TrustGraph public repository contains persistent storage infrastructure including Cassandra-backed graph/knowledge components and dedicated vector-store integrations.

Its vector-store lifecycle documentation describes physical collections being created when vectors are first written and supports multiple physical collections for embeddings with different dimensions.

The benchmark will therefore instrument the actual enabled backends rather than estimate TrustGraph memory usage from source code alone.

Relevant measurements may include:

```text
Cassandra data size
vector-store collection size
index size
process RSS
container memory
retrieved graph/context size
```

The exact deployment configuration will be recorded with every published result.

---

# ASM-CM measurements

ASM-CM experiments will report:

```text
retained neural state bytes
snapshot size
runtime RSS
VRAM
write latency
query latency
retrieval quality
reader context size
```

At each history checkpoint the benchmark will additionally calculate:

```text
additional disk bytes / additional events
additional logical-state bytes / additional events
Δ idle RSS / Δ events
Δ query-peak RSS / Δ events
```

The ASM-CM hypothesis is specifically that the first quantity may remain
positive while the logical associative-state slope approaches zero. Retrieval
quality is a separate gate: a bounded state that ceases to retrieve useful
information does not establish useful long-duration memory.

The frozen accounting specification is documented in
[methodology/asm_cm_disk_vs_working_memory.md](methodology/asm_cm_disk_vs_working_memory.md).

The LongMemEval-S accuracy-versus-context control freezes top-15 rankings and evaluates
ASM-CM, its three RRF hybrids, Vector, BM25, Vector+BM25 RRF, TrustGraph and two
non-retrieval controls at 2k, 4k, 8k, 16k and 28k evidence tokens with the same GPT-4o
reader. Its protocol, audit correction and interpretation
rules are documented in
[methodology/longmemeval_fixed_context_budget.md](methodology/longmemeval_fixed_context_budget.md).

The currently observed retained-state figure of approximately **140 KiB** is treated as a prior measured result, not a guaranteed outcome of every benchmark configuration.

The benchmark must independently verify retained-state size during each run.

---

# Reproducibility

Every published benchmark run should preserve:

- git commit hashes;
- container images;
- configuration files;
- dataset fingerprint;
- hardware;
- operating system;
- CPU;
- RAM;
- GPU;
- CUDA version where applicable;
- database configuration;
- embedding model;
- reader model;
- random seed;
- event count;
- query count.

Raw measurements should be stored before aggregation.

---

# Proposed repository structure

```text
persistent-memory-scaling-benchmark/
├── README.md
├── LICENSE
├── methodology/
│   ├── definitions.md
│   ├── accounting.md
│   ├── workloads.md
│   └── fairness.md
│
├── adapters/
│   ├── trustgraph/
│   └── asm_cm/
│
├── workloads/
│   ├── synthetic/
│   └── longmemeval/
│
├── runners/
│   ├── ingest.py
│   ├── query.py
│   └── measure.py
│
├── metrics/
│   ├── storage.py
│   ├── memory.py
│   ├── latency.py
│   └── retrieval.py
│
├── results/
│   └── README.md
│
├── plots/
│
└── scripts/
    ├── run_trustgraph.sh
    ├── run_asm_cm.sh
    └── run_full_benchmark.sh
```

---

# What this benchmark is not

This repository is not intended to prove that:

- graph memory is obsolete;
- ASM-CM replaces databases;
- ASM-CM replaces RAG;
- TrustGraph is inefficient;
- bounded state is automatically better than explicit storage;
- one architecture should be used for every workload.

The benchmark measures trade-offs.

If TrustGraph wins a metric, that result will be published.

If ASM-CM loses a metric, that result will also be published.

---

# Initial success criteria

The first benchmark release is complete when it can reproducibly answer:

1. How does persistent storage grow with history for each system?
2. How does resident memory grow?
3. How does retained per-agent state grow?
4. Does retrieval latency change with history length?
5. Does write latency change with history length?
6. Does retrieval quality degrade as history grows?
7. How much context must each system send to the reader?
8. What is the incremental cost of adding another independent agent?
9. Which capabilities are obtained in exchange for those resource costs?

---

# Why this matters

An AI agent may eventually accumulate:

- months of conversations;
- millions of events;
- long-running workflows;
- user preferences;
- decisions;
- corrections;
- relationships;
- environmental observations.

At that scale, saying that a system has "persistent memory" is not enough.

The engineering question becomes:

> **What grows when the history grows?**

The answer may determine whether an architecture can support ten persistent agents or ten million.

This benchmark exists to measure that difference.

---

# Implementation status

The work is intentionally sequenced in two stages:

1. complete the standalone TrustGraph benchmark, including free-language
   ingestion and retrieval;
2. add the paired ASM-CM comparison only after ASM Memory Bridge promotes a
   reliable free-language retrieval contract.

The inspected TrustGraph upstream and phased implementation plan are recorded
in [methodology/trustgraph_implementation_plan.md](methodology/trustgraph_implementation_plan.md).
Execution status, dependencies and promotion gates are tracked in
[ROADMAP.md](ROADMAP.md).
