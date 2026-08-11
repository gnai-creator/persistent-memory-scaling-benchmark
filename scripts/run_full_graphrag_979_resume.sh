#!/usr/bin/env bash
set -euo pipefail

token_file="/tmp/pmsb-fullgraphrag-token-v2"
if [[ ! -r "$token_file" ]]; then
  printf 'TrustGraph token file is not readable: %s\n' "$token_file" >&2
  exit 2
fi
IAM_BOOTSTRAP_TOKEN=""
IFS= read -r IAM_BOOTSTRAP_TOKEN < "$token_file" || [[ -n "$IAM_BOOTSTRAP_TOKEN" ]]
if [[ -z "$IAM_BOOTSTRAP_TOKEN" ]]; then
  printf 'TrustGraph token file is empty: %s\n' "$token_file" >&2
  exit 2
fi
export IAM_BOOTSTRAP_TOKEN

repo_root="/home/felipe/dev/ai/gitlab/persistent-memory-scaling-benchmark"
cd "$repo_root"
"$repo_root/scripts/ensure_trustgraph_ollama.sh"
exec .venv/bin/python -m persistent_memory_scaling.trustgraph.phase81_full_graphrag \
  --flow pmsb-fullgraph-qwen3-bounded-v1 \
  --ensure-flow-model qwen3:14b-pmsb-bounded \
  --ensure-flow-embeddings-model sentence-transformers/all-MiniLM-L6-v2 \
  --collection pmsb-phase81-fullrun-bounded-v1 \
  --asm-root /home/felipe/dev/ai/gitlab/asm-memory-bridge \
  --multiwoz-root /home/felipe/dev/ai/gitlab/MultiWOZ \
  --phase8-results /home/felipe/dev/ai/gitlab/asm-memory-bridge/runs/asm_memory_bridge_phase8_supported/results.json \
  --output "$repo_root/results/raw/tg-phase81-full-graphrag-full-v2.json" \
  --resume \
  --max-attempts 0 \
  --retry-delay-seconds 330 \
  --max-retry-delay-seconds 600 \
  --request-timeout-seconds 600
