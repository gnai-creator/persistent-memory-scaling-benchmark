#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
token_file="${PMSB_TG_TOKEN_FILE:-/tmp/pmsb-fullgraphrag-token-v2}"
[[ -r "$token_file" ]] || { printf 'TrustGraph token file is not readable: %s\n' "$token_file" >&2; exit 2; }
full_flow="${PMSB_TG_FULL_FLOW_GPT4O:-pmsb-fullgraph-gpt4o-v1}"
IFS= read -r IAM_BOOTSTRAP_TOKEN < "$token_file" || [[ -n "${IAM_BOOTSTRAP_TOKEN:-}" ]]
[[ -n "${IAM_BOOTSTRAP_TOKEN:-}" ]] || { printf '%s\n' 'TrustGraph token is empty' >&2; exit 2; }
export IAM_BOOTSTRAP_TOKEN
cd "$repo_root"
exec .venv/bin/python -m persistent_memory_scaling.trustgraph.phase81_full_graphrag \
  --corpus longmemeval500 \
  --flow "$full_flow" \
  --ensure-flow-model gpt-4o \
  --ensure-flow-embeddings-model "${PMSB_TG_EMBEDDINGS_MODEL:-nomic-embed-text}" \
  --collection pmsb-longmemeval500-full-graphrag-gpt4o \
  --asm-root /home/felipe/dev/ai/gitlab/asm-memory-bridge \
  --dataset /home/felipe/dev/ai/gitlab/ASM/data/longmemeval/longmemeval_s_cleaned.json \
  --oracle-dataset /home/felipe/dev/ai/gitlab/ASM/data/longmemeval/longmemeval_oracle.json \
  --official-evaluator-root /home/felipe/dev/ai/gitlab/LongMemEval \
  --official-python /home/felipe/dev/ai/gitlab/LongMemEval/.venv/bin/python \
  --phase8-results /home/felipe/dev/ai/gitlab/asm-memory-bridge/runs/asm_bridge81_longmemeval_gpt4o/results.json \
  --output "$repo_root/results/raw/tg-longmemeval-s-500-full-graphrag-gpt4o.json" \
  --resume --max-attempts 0 --retry-delay-seconds 330 \
  --max-retry-delay-seconds 600 --request-timeout-seconds 600
