#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
asm_root="${PMSB_ASM_ROOT:-/home/felipe/dev/ai/gitlab/asm-memory-bridge}"
[[ -n "${OPENAI_API_KEY:-}" ]] || { printf '%s\n' 'OPENAI_API_KEY must be exported' >&2; exit 2; }

cd "$repo_root"
exec .venv/bin/python -m persistent_memory_scaling.longmemeval_fixed_context \
  --asm-root "$asm_root" \
  --dataset /home/felipe/dev/ai/gitlab/ASM/data/longmemeval/longmemeval_s_cleaned.json \
  --oracle-dataset /home/felipe/dev/ai/gitlab/ASM/data/longmemeval/longmemeval_oracle.json \
  --asm-results "$asm_root/runs/asm_bridge81_longmemeval_hybrids/results.json" \
  --trustgraph-results "$repo_root/results/raw/tg-longmemeval-s-500-graph-embeddings-gpt4o.json" \
  --official-evaluator-root /home/felipe/dev/ai/gitlab/LongMemEval \
  --official-python /home/felipe/dev/ai/gitlab/LongMemEval/.venv/bin/python \
  --output "$repo_root/results/raw/longmemeval-fixed-context-budget.json" \
  --resume \
  "$@"
