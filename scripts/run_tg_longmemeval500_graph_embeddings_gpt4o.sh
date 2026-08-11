#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
token_file="${PMSB_TG_TOKEN_FILE:-/tmp/pmsb-fullgraphrag-token-v2}"
[[ -r "$token_file" ]] || { printf 'TrustGraph token file is not readable: %s\n' "$token_file" >&2; exit 2; }
[[ -n "${OPENAI_API_KEY:-}" ]] || { printf '%s\n' 'OPENAI_API_KEY must be exported for the paired GPT-4o reader' >&2; exit 2; }
IFS= read -r IAM_BOOTSTRAP_TOKEN < "$token_file" || [[ -n "${IAM_BOOTSTRAP_TOKEN:-}" ]]
[[ -n "${IAM_BOOTSTRAP_TOKEN:-}" ]] || { printf '%s\n' 'TrustGraph token is empty' >&2; exit 2; }
export IAM_BOOTSTRAP_TOKEN
cd "$repo_root"
exec .venv/bin/python -m persistent_memory_scaling.trustgraph.phase81_paired \
  --corpus longmemeval500 \
  --flow "${PMSB_TG_EMBEDDINGS_FLOW:-pmsb-fullgraph-qwen3-v2}" \
  --collection pmsb-longmemeval500-graph-embeddings \
  --asm-root /home/felipe/dev/ai/gitlab/asm-memory-bridge \
  --dataset /home/felipe/dev/ai/gitlab/ASM/data/longmemeval/longmemeval_s_cleaned.json \
  --oracle-dataset /home/felipe/dev/ai/gitlab/ASM/data/longmemeval/longmemeval_oracle.json \
  --official-evaluator-root /home/felipe/dev/ai/gitlab/LongMemEval \
  --official-python /home/felipe/dev/ai/gitlab/LongMemEval/.venv/bin/python \
  --phase8-results /home/felipe/dev/ai/gitlab/asm-memory-bridge/runs/asm_bridge81_longmemeval_gpt4o/results.json \
  --output "$repo_root/results/raw/tg-longmemeval-s-500-graph-embeddings-bridge81-gpt4o.json" \
  --resume
