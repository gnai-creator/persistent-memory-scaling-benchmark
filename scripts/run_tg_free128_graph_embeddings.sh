#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
token_file="${PMSB_TG_TOKEN_FILE:-/tmp/pmsb-fullgraphrag-token-v2}"
[[ -r "$token_file" ]] || { printf 'TrustGraph token file is not readable: %s\n' "$token_file" >&2; exit 2; }
IFS= read -r IAM_BOOTSTRAP_TOKEN < "$token_file" || [[ -n "${IAM_BOOTSTRAP_TOKEN:-}" ]]
[[ -n "${IAM_BOOTSTRAP_TOKEN:-}" ]] || { printf '%s\n' 'TrustGraph token is empty' >&2; exit 2; }
export IAM_BOOTSTRAP_TOKEN
cd "$repo_root"
exec .venv/bin/python -m persistent_memory_scaling.trustgraph.phase81_paired \
  --corpus free128 \
  --flow "${PMSB_TG_EMBEDDINGS_FLOW:-pmsb-fullgraph-qwen3-v2}" \
  --collection pmsb-free128-graph-embeddings \
  --asm-root /home/felipe/dev/ai/gitlab/asm-memory-bridge \
  --retrieval-root /home/felipe/dev/ai/gitlab/asm-memory-bridge/data/dual_asm_retrieval_v1 \
  --phase8-results /home/felipe/dev/ai/gitlab/asm-memory-bridge/runs/dual_asm_r32/results.json \
  --reader-protocol-results /home/felipe/dev/ai/gitlab/asm-memory-bridge/runs/asm_memory_bridge_phase8_supported/results.json \
  --output "$repo_root/results/raw/tg-r32-free-language-graph-embeddings.json" \
  --resume
