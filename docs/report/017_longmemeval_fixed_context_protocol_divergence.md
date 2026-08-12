# LongMemEval-S fixed-context protocol divergence audit

**Date:** 12 August 2026
**Status:** completed protocol audit; causal packaging ablation still pending

## Why this audit was required

An earlier TrustGraph graph-embeddings run reported 70.0% official GPT-4o judge
accuracy. The frozen fixed-context endpoints later measured 39.0% at a 2,000-token
evidence budget and 33.6% at a 28,000-token evidence budget. This gap is too large to
treat as sampling variation or to present as directly comparable measurements.

## What changed

The 70.0% artifact was produced without the Memory Bridge 8.1
`evidence_transform`. It is therefore an **uncompacted high-context ablation**, not a
same-compactor endpoint. It used, on average:

- 27,928.1 GPT-4o input tokens per question;
- 5.30 seconds of reader latency per question;
- 96.48% frozen Recall@15;
- 70.0% official answer accuracy.

The fixed-context runner reused the frozen TrustGraph ranking but rebuilt the evidence
package with deterministic `o200k_base` token budgets and the token-budget compactor.
At the two published endpoints it measured:

| Endpoint | Official accuracy | Mean reader input | Mean reader latency |
|---|---:|---:|---:|
| TrustGraph uncompacted high-context | 70.0% | 27,928.1 | 5.30 s |
| TrustGraph fixed 2K | 39.0% | approximately 2.3K | 2.04 s |
| TrustGraph fixed 28K | 33.6% | approximately 28.9K | 5.38 s |

The retrieval ranking itself did not change: all 500 fixed-context TrustGraph rankings
match the source artifact. The post-retrieval representation did change materially:

- identical frozen rankings: 500/500;
- identical final evidence-ID lists at 28K: 49/500;
- identical generated predictions at 28K: 84/500;
- mean reader-input difference at 28K versus the uncompacted run: +941.9 tokens.

Consequently, the divergence is downstream of candidate retrieval. Evidence packing,
token-boundary truncation, memory-boundary behavior and the resulting reader prompt are
the material protocol differences. The current evidence does not isolate which one is
individually responsible for the full accuracy delta.

## Interpretation of the fixed-context endpoints

Within this frozen protocol, increasing the evidence budget from 2K to 28K increased
reader latency and reduced official answer accuracy for four of five systems:

| System | 2K | 28K | Change |
|---|---:|---:|---:|
| ASM-CM + Bridge 8.1 | 12.2% | 22.4% | +10.2 points |
| Vector + Bridge 8.1 | 43.6% | 38.4% | -5.2 points |
| BM25 + Bridge 8.1 | 44.6% | 29.8% | -14.8 points |
| Vector + BM25 RRF + Bridge 8.1 | 44.2% | 35.6% | -8.6 points |
| TrustGraph graph-embeddings | 39.0% | 33.6% | -5.4 points |

The correct conclusion is protocol-scoped:

> Under this frozen fixed-context protocol, 14 times more evidence increased reader
> latency but reduced official answer accuracy for four of five systems. ASM-CM was the
> only system to improve, consistent with relevant evidence becoming reachable deeper
> in its frozen ranking.

The ASM result must not be described as a change in frozen Recall@15. Rankings and
Recall@15 are constant across budgets. The defensible mechanism is **budget
reachability**: a larger evidence package can expose candidates located deeper in the
same ranking. A dedicated rank-at-budget analysis is needed before attributing the gain
entirely to that mechanism.

## Publication rules

1. Label the 70.0% result `TrustGraph graph-embeddings (uncompacted high-context)`.
2. Label 39.0% and 33.6% as fixed-context endpoints at 2K and 28K.
3. Do not put the 70.0% value on the fixed-context curve as if it were another budget
   point.
4. State that retrieval rankings were identical while evidence packages were not.
5. Separate frozen Recall@15 from budget reachability.
6. Do not claim that additional evidence generally harms accuracy outside this measured
   protocol.

## Next diagnostic

The minimal causal follow-up should replay the TrustGraph ranking with a crossed packing
matrix:

1. original uncompacted packaging;
2. original whole-memory byte-boundary packaging;
3. fixed token-budget packaging without partial-memory truncation;
4. current token-budget packaging with partial-memory truncation.

The same reader contract, question order and evaluator must be retained. This will
separate the effect of the Bridge transform from boundary and truncation semantics.

## Canonical artifacts

- source 70% run: `results/raw/tg-longmemeval-s-500-graph-embeddings-gpt4o.json`;
- fixed endpoints: `results/raw/longmemeval-fixed-context-2k-28k.json`;
- methodology: `methodology/longmemeval_fixed_context_budget.md`;
- endpoint chart: `docs/screens/longmemeval-fixed-context-2k-28k.png`;
- marginal-context chart: `docs/screens/longmemeval-fixed-context-delta.png`.
