# TrustGraph vs. ASM-CM: What 2,500 GitHub Stars Don't Tell You About Memory, Reliability, and Integration Cost

Persistent AI memory is not a single engineering problem.

A system can store explicit facts, maintain learned associative state, archive canonical
payloads, retrieve evidence, or assemble context for a reader LLM. Each design places its
cost somewhere different: RAM, VRAM, disk, databases, indexes, latency, or reader tokens.

That is why I built a reproducible benchmark comparing two fundamentally different
approaches.

**TrustGraph** represents knowledge through explicit graph, vector, and database
infrastructure. Its strengths include addressable relationships, provenance, structured
inspection, and graph-native retrieval.

**ASM-CM** represents associations inside a compact learned neural state. The Memory
Bridge keeps canonical payloads separate and sends selected evidence to the reader.

In one sentence:

> **Graph reification turns memories into explicit addressable facts. ASM-CM turns
> experience into an evolving learned state.**

Neither approach is automatically better. The question is what happens when both are
measured.

## The paired result

The central experiment used the same 979 support-valid MultiWOZ questions, closed
16-memory candidate bundles, top-k = 5, the same Qwen3 14B reader, prompt, evaluator, and
actual reader-token accounting.

| System | Recall@5 | Answer score | Reader input |
|---|---:|---:|---:|
| **ASM-CM + Memory Bridge 8.1** | **93.56%** | **66.59%** | **1,070,228** |
| TrustGraph graph embeddings | 60.47% | 44.22% | 2,002,598 |
| Vector RAG | 69.97% | 49.68% | 1,994,408 |
| BM25 | 75.89% | 56.85% | 2,148,717 |

Under this protocol, ASM-CM + Bridge achieved:

- **+33.09 percentage points** Recall@5 over TrustGraph graph embeddings;
- **+22.37 percentage points** answer score;
- approximately **46.6% fewer** reader-input tokens.

This result evaluates **TrustGraph graph-embeddings retrieval**, not TrustGraph as a
whole and not the complete Full GraphRAG pipeline.

## Operational latency

TrustGraph graph embeddings averaged:

- 178.5 ms for retrieval;
- 1,235.6 ms for the shared reader;
- 1,414.1 ms combined.

The ASM-CM + Bridge operational replay averaged approximately 1,294.1 ms/question from
total wall time. TrustGraph was 9.3% slower before preparation and 10.9% slower after
amortizing 21.2 seconds of collection setup, ingestion, and indexing readiness.

An intermediate partial estimate suggested an 18–20% difference. The completed run did
not confirm it, so I replaced that estimate with the final 9.3%/10.9% result.

## Where the infrastructure cost appeared

TrustGraph persistent storage grew from 2.14 MB at 100 events to 1.805 GB at 100,000
events. The measured curve was consistent with approximately linear storage growth—not
exponential growth.

The TrustGraph stack used:

- approximately **4.81 GB peak container RAM** at c100k during the scaling window;
- approximately **4.27 GB mean container RAM** during a separate 30-second idle window;
- **0 B of attributable TrustGraph VRAM** in the structured path measured.

Mean and peak RAM are different statistics. Device VRAM also cannot be converted into
TrustGraph VRAM by subtracting two unrelated windows.

The ASM Phase 8.1 Bridge replay peaked at 115.3 MB RSS with its Qwen3 reader measured
separately. That is an operational reference, not an ASM 100→100k scaling curve.

## The ASM result that should not be hidden

ASM-CM did not win every experiment.

In the paired synthetic TG-2 c100 adapter run, it achieved only **8.75% Recall@5**,
required **30.01 seconds per ingested event**, and averaged **3.586 seconds per query**.
That implementation was too slow and too inaccurate to justify running the same path to
100k events.

The logical neural state was compact, but compact state alone does not demonstrate useful
memory scaling.

> **ASM-CM currently has lower single-instance ingestion throughput because updates are
> sequential within a causal stream. Independent namespaces can be distributed across
> parallel workers, but horizontal scaling was not evaluated in this benchmark.**

That is a plausible scaling path for aggregate multi-agent throughput, not a substitute
for improving single-stream performance.

## Full GraphRAG is a separate result

The valid Full GraphRAG diagnostic currently contains only 10 questions and must not be
presented as the final 979-question result.

It measured:

- 50% grounding Recall@5, recovered through official explainability output;
- 21.05% answer score;
- 19.53 seconds/question mean latency;
- zero directly mappable public-response sources in 10/10 answers.

The attempted full continuation encountered HTTP 504 during concurrent GPU saturation.
That sequence is preserved as an integration diagnostic, not treated as an isolated
TrustGraph reliability rate. The complete Full GraphRAG and DocumentRAG controls remain
pending and are excluded from the main conclusion.

## What can be concluded

In this paired structured workload, ASM-CM + Memory Bridge achieved higher retrieval
quality, higher answer quality, lower reader-context volume, and lower operational
latency than TrustGraph graph-embeddings retrieval.

TrustGraph retained important architectural strengths: explicit representation,
addressable provenance, and graph-native inspection. In the tested deployment, those
properties came with measurable RAM, storage, preparation, and integration costs.

This does **not** establish universal superiority over TrustGraph. MultiWOZ uses
structured language; Full GraphRAG is not complete; DocumentRAG controls are pending;
hardware and runtime conditions are specific; and ASM free-language retrieval remains a
separate, unresolved line of work.

The result is narrower—and more useful—than a universal claim:

> **Under the tested protocol, compact neural associative memory did not trade retrieval
> quality for efficiency. It improved both. Under another workload, its current update
> path became the limiting factor.**

## Read the evidence

The full article contains the complete methodology, resource accounting, invalid-run
exclusions, limitations, hashes, and reproduction notes.

- **Full technical article:** `PUBLIC_ARTICLE_URL`
- **Public benchmark repository:** `PUBLIC_REPOSITORY_URL`

Before publication, replace both placeholders and verify the dated GitHub-star count in
the title. The star count is editorial context, not a technical metric.

*This benchmark began with a disagreement. It ends with reproducible artifacts.*
