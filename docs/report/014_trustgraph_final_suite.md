# TrustGraph final sequential suite

The final TrustGraph executions are intentionally serialized to avoid the GPU and Ollama
contention observed during the first Full GraphRAG attempt. The orchestrator is:

```bash
scripts/run_trustgraph_final_suite.sh --preflight
scripts/run_trustgraph_final_suite.sh
```

It performs a complete preflight before starting the first expensive stage. If any stage runner is
missing or not executable, it exits with status `3` without running anything. It uses a local lock
to prevent two suite instances, writes one append-only log per stage, and invokes every runner in
resume mode through its stage wrapper.

The sequence is:

1. MultiWOZ Phase 8.1 Full GraphRAG — 979 questions;
2. free-language graph-embeddings — 128 questions;
3. free-language Full GraphRAG — 128 questions;
4. LongMemEval-S graph-embeddings + GPT-4o — 500 questions;
5. LongMemEval-S Full GraphRAG + GPT-4o — 500 questions.

The orchestrator does not inspect, start, stop, signal, or otherwise control ASM processes.

Use `--from STAGE` to resume at a stage after a verified completed output. Individual runners are
also responsible for per-question checkpoints, so restarting the same stage must not discard
completed rows.

All five stages now have implemented runners. The two corpus adapters verify the exact frozen ID
order and cardinality (128 and 500) before ingestion. Both LongMemEval runners invoke the official
GPT-4o judge only after all 500 predictions exist.

The deployed TrustGraph text-completion workers are Ollama processors. Immediately before the
LongMemEval Full GraphRAG stage, the suite recreates only TrustGraph's `text-completion` service
with the explicit OpenAI processor configuration and `gpt-4o`; cleanup restores the original
Ollama service. This switch does not control ASM or Ollama processes outside the TrustGraph Compose
project. A flow name alone is not treated as evidence that GPT-4o was used.

The suite reads `OPENAI_API_KEY` from the current environment or, by default, the Memory Bridge
`.env` during preflight. Secrets are not passed on command lines or written to result artifacts.
