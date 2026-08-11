#!/usr/bin/env bash
set -euo pipefail

endpoint="${PMSB_TG_OLLAMA_HOST:-http://172.19.0.1:11435}"
model="${PMSB_TG_BOUNDED_MODEL:-qwen3:14b-pmsb-bounded}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
modelfile="$repo_root/configs/trustgraph/qwen3-14b-bounded.Modelfile"

if ! curl -fsS --max-time 3 "$endpoint/api/version" >/dev/null; then
  systemctl --user reset-failed pmsb-ollama-trustgraph.service 2>/dev/null || true
  systemd-run --user --unit=pmsb-ollama-trustgraph --property=Restart=on-failure \
    --setenv=OLLAMA_HOST="${endpoint#http://}" /usr/local/bin/ollama serve
  for _ in $(seq 1 30); do
    curl -fsS --max-time 2 "$endpoint/api/version" >/dev/null && break
    sleep 1
  done
fi
curl -fsS --max-time 3 "$endpoint/api/version" >/dev/null || {
  printf 'Dedicated TrustGraph Ollama is unavailable: %s\n' "$endpoint" >&2
  exit 2
}
if ! OLLAMA_HOST="$endpoint" ollama show "$model" >/dev/null 2>&1; then
  OLLAMA_HOST="$endpoint" ollama create "$model" -f "$modelfile"
fi
printf 'TrustGraph Ollama ready: %s model=%s\n' "$endpoint" "$model"
