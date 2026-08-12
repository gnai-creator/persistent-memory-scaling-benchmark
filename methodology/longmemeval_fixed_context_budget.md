# LongMemEval-S fixed-context budget control

## Question

The completed TrustGraph graph-embeddings run obtained higher official answer accuracy
while sending much more context to GPT-4o. This control asks:

> How much answer accuracy does each frozen retrieval ranking buy at the same reader
> evidence budget?

It is designed to distinguish retrieval/ranking quality from gains caused by exposing
more evidence to the reader. It does not change or retrain any retriever.

## Trigger and audit correction

An implementation audit found that the first completed TrustGraph LongMemEval-S
graph-embeddings runner called `evaluate_one` without passing the Bridge 8.1
`evidence_transform`. The resulting artifact is internally valid, but it is an
**uncompacted high-context ablation**, not a same-compactor comparison:

- Recall@15: 96.48%;
- official GPT-4o accuracy: 70.00%;
- mean reader input: 27,928.1 tokens/question;
- mean GPT-4o reader latency: 5.30 seconds/question.

The artifact is preserved rather than overwritten. Its charts and prose must carry the
label `TrustGraph graph-embeddings (uncompacted)`. A corrected Bridge 8.1 compact rerun
uses a separate output path.

## Frozen comparison matrix

The control is executed in two resumable stages. The first stage evaluates five
candidate generators:

1. ASM-CM + Memory Bridge 8.1;
2. Vector + Memory Bridge 8.1;
3. BM25 + Memory Bridge 8.1;
4. Vector + BM25 equal-weight RRF + Memory Bridge 8.1;
5. TrustGraph graph-embeddings.

After that matrix completes, the checkpoint is expanded with three ASM hybrid rankings:

6. ASM + Vector equal-weight RRF + Memory Bridge 8.1;
7. ASM + BM25 equal-weight RRF + Memory Bridge 8.1;
8. ASM + Vector + BM25 equal-weight RRF + Memory Bridge 8.1.

The hybrids are required because all three outperformed standalone ASM-CM on the
completed compact LongMemEval-S evaluation. They remain scientifically relevant even
though none exceeded the strongest Vector + BM25 control at that earlier point.

Two non-retrieval controls are added in the same second stage:

9. canonical full-history order, truncated only by the fixed token budget;
10. deterministic random history order, truncated by the same budget.

These controls test whether a retrieval ranking adds measurable value over directly
transporting history or selecting history without relevance information.

For every system, the top-15 memory IDs are reused from completed artifacts. Retrieval
is not rerun, and neither the answer nor the gold memory IDs are visible to ranking or
budget allocation. The same 500 LongMemEval-S questions and the same GPT-4o reader are
used throughout.

## Evidence budgets

The fixed budgets are:

```text
2,000
4,000
8,000
16,000
28,000
```

The unit is `o200k_base` tokens in the joined evidence **content**. Ranked memories are
packed in order. If the next memory exceeds the remaining budget, its content is
truncated at the tokenizer boundary; later memories are omitted after the budget is
exhausted. No generation, rewriting, answer matching or gold-aware selection occurs in
this step.

Evidence-content tokens are not the same as the provider's complete prompt tokens. The
system instruction, question, timestamps, memory IDs, source IDs and formatting add a
small overhead. Therefore every row records both:

- `evidence_token_budget` and `evidence_tokens_o200k`;
- `reader_input_tokens`, as reported by the OpenAI API.

This distinction makes the limit deterministic while preserving the billable/operational
reader measurement.

## Measurements and interpretation

For each system × budget point, report:

- Recall@15 from the frozen ranking;
- official LongMemEval GPT-4o judge accuracy;
- diagnostic answer metrics;
- mean and total reader input tokens;
- mean reader latency;
- evidence tokens actually used;
- completion and failure counts.

Retrieval latency is intentionally set to zero in this replay because retrieval is not
executed. These rows must never be used to claim a retrieval-latency advantage. Their
purpose is the accuracy-versus-context curve.

The primary interpretation is the curve, not a single endpoint:

- accuracy at equal context;
- marginal accuracy gained from each larger budget;
- accuracy points per 1,000 reader input tokens;
- whether rankings converge or remain separated as budget grows;
- whether the 28k TrustGraph result can be reproduced when every retriever receives the
  same allowance.

If TrustGraph remains ahead at equal budgets, that supports a ranking-quality advantage.
If the gap narrows or disappears, the earlier accuracy gain was substantially purchased
with additional reader context. Either outcome is publishable.

## Completeness rules

The first stage contains 25 configurations and 12,500 reader answers. The expanded final
matrix contains 50 configurations and 25,000 reader answers. Partial rows are checkpoints
only. The first-stage result may be analyzed after its official evaluation completes,
but the final ten-system chart is not promoted until all 25,000 rows and the expanded
official evaluation are complete. The runner is resumable, accepts only an additive
system expansion, and rejects changes to questions, budgets or other frozen fields.

## Reproduction

Install the tokenizer dependency and export `OPENAI_API_KEY`, then run:

```bash
cd /home/felipe/dev/ai/gitlab/persistent-memory-scaling-benchmark
.venv/bin/pip install -e '.[fixed-context]'
scripts/run_longmemeval_fixed_context.sh
```

Canonical implementation and artifacts:

- runner: `src/persistent_memory_scaling/longmemeval_fixed_context.py`;
- launcher: `scripts/run_longmemeval_fixed_context.sh`;
- checkpoint/final result: `results/raw/longmemeval-fixed-context-budget.json`;
- runtime log: `results/logs/longmemeval-fixed-context/run.log`;
- source ASM/hybrid rankings:
  `asm-memory-bridge/runs/asm_bridge81_longmemeval_hybrids/results.json`;
- source TrustGraph ranking:
  `results/raw/tg-longmemeval-s-500-graph-embeddings-gpt4o.json`.

The source TrustGraph answer artifact is uncompacted, but only its frozen retrieved IDs
are reused. All systems receive newly assembled evidence under the same budget rule.

## Completed divergence audit

The completed 2K/28K replay confirms that the earlier 70.0% TrustGraph result must not
be mixed with the fixed-context endpoints. The ranking is identical in all 500
questions, but at 28K the final evidence-ID list is identical in only 49/500 cases and
the generated prediction is identical in only 84/500 cases. Mean reader input also
differs by +941.9 tokens in the fixed replay.

This localizes the divergence downstream of retrieval, to evidence packaging,
token-boundary truncation, memory-boundary behavior and the resulting reader prompt. It
does not yet isolate the contribution of each factor. See
`docs/report/017_longmemeval_fixed_context_protocol_divergence.md` for the audit and its
publication rules.

The frozen Recall@15 value is invariant across evidence budgets. Any improvement caused
by a larger package must therefore be described as improved **budget reachability** of
deeper ranked evidence, not as an increase in retrieval recall.

## Completed pre-control accounting

Before the budget-matched reader rerun, an offline symmetric accounting pass compares
all completed systems. It reports exact `evidence_bytes / complete_history_bytes`,
provider input tokens, official accuracy, accuracy points per 1,000 input tokens and
input tokens per accuracy point. This calculation requires no new LLM calls and is stored
in `results/raw/longmemeval-all-context-efficiency.json`.

The provider-input/history-token ratio is reported separately from the evidence-byte
fraction because provider input includes the question, system prompt, provenance fields
and formatting. It must not be mislabeled as an evidence-only percentage.
