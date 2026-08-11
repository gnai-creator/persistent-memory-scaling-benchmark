#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
generated="$repo_root/configs/trustgraph/generated"
base="$generated/docker-compose.yaml"
override="$generated/compose.openai-text-completion.override.yaml"
mode="${1:-}"
case "$mode" in
  openai)
    : "${OPENAI_API_KEY:?OPENAI_API_KEY must be exported before switching TrustGraph to OpenAI}"
    docker compose -f "$base" -f "$override" up -d --force-recreate text-completion
    ;;
  ollama)
    docker compose -f "$base" up -d --force-recreate text-completion
    ;;
  *) printf '%s\n' 'Usage: scripts/switch_trustgraph_text_completion.sh openai|ollama' >&2; exit 2 ;;
esac
