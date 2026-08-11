# LongMemEval-S fixed-context control — implementation record

## Status

The fixed-context control is implemented, tested and running as a resumable background
service. At the recorded inspection on 2026-08-11, both the corrected compact
TrustGraph rerun and the fixed-context control were active. The fixed-context artifact
contained 49 of 12,500 reader rows. This count is a progress snapshot, not a result.

No accuracy conclusion is authorized until the reader matrix and official evaluation
are complete.

## What was corrected

The first completed TrustGraph LongMemEval-S graph-embeddings artifact did not apply the
Bridge 8.1 evidence transform. Its 70.00% official accuracy and 27,928.1 mean input
tokens remain measured facts, but the run is now classified as:

> TrustGraph graph-embeddings (uncompacted high-context ablation)

It must not be described as using the same compactor as the seven compact internal
systems. The original artifact remains unchanged for auditability. The corrected compact
run writes to `tg-longmemeval-s-500-graph-embeddings-bridge81-gpt4o.json`.

## Implemented experiment

The new control crosses five frozen rankings with five evidence budgets:

| Rankings | Evidence budgets |
|---|---|
| ASM-CM + Bridge 8.1 | 2k, 4k, 8k, 16k, 28k |
| Vector + Bridge 8.1 | 2k, 4k, 8k, 16k, 28k |
| BM25 + Bridge 8.1 | 2k, 4k, 8k, 16k, 28k |
| Vector + BM25 RRF + Bridge 8.1 | 2k, 4k, 8k, 16k, 28k |
| TrustGraph graph-embeddings | 2k, 4k, 8k, 16k, 28k |

All configurations use the same 500 questions, top-15 frozen rankings, GPT-4o reader
and official GPT-4o judge. Ranking and context allocation are gold-blind.

The limit applies to evidence-content tokens under `o200k_base`. Provider-reported total
input tokens are recorded separately because the complete prompt also contains the
system instruction, question, provenance fields and formatting.

## Validation

- tokenizer dependency installed explicitly;
- unit test verifies that packed evidence never exceeds its budget;
- complete repository test suite: 41 passed;
- smoke: one question × five systems at 2k completed 5/5;
- observed total inputs in the smoke: 2,271–2,345 tokens, consistent with the 2k
  evidence allowance plus prompt/provenance overhead;
- canonical run writes an atomic checkpoint after every reader answer;
- resume is rejected if the frozen protocol changes.

## Operational separation

The control reads completed ASM and TrustGraph ranking artifacts. It does not attach to,
stop, restart or mutate an existing ASM-CM process. It performs new GPT-4o reader calls
in a separate process. Retrieval latency is excluded because retrieval is replayed from
frozen IDs.

## Publication rule

Until completion, charts may describe the protocol and show the prior uncompacted point,
but may not show partial fixed-budget accuracy as a final result. After completion, the
publication should plot accuracy against both enforced evidence budget and measured
total reader input, with every system on the same axes.

Full frozen methodology:
[longmemeval_fixed_context_budget.md](../../methodology/longmemeval_fixed_context_budget.md).
