#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log_root="$repo_root/results/logs/trustgraph-final-suite"
lock_dir="$repo_root/results/.trustgraph-final-suite.lock"
start_at="${PMSB_START_AT:-phase81_full}"
dry_run=0
preflight_only=0
text_completion_switched=0
env_file="${PMSB_ENV_FILE:-/home/felipe/dev/ai/gitlab/asm-memory-bridge/.env}"

usage() {
  printf '%s\n' \
    'Usage: scripts/run_trustgraph_final_suite.sh [--preflight] [--dry-run] [--from STAGE]' \
    '' \
    'Stages (always sequential):' \
    '  phase81_full' \
    '  free128_graph_embeddings' \
    '  free128_full_graphrag' \
    '  longmemeval500_graph_embeddings' \
    '  longmemeval500_full_graphrag' \
    '' \
    'The suite never starts, stops, or signals an ASM process.'
}

while (($#)); do
  case "$1" in
    --preflight) preflight_only=1 ;;
    --dry-run) dry_run=1 ;;
    --from)
      shift
      [[ $# -gt 0 ]] || { printf '%s\n' '--from requires a stage' >&2; exit 2; }
      start_at="$1"
      ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

stages=(
  phase81_full
  free128_graph_embeddings
  free128_full_graphrag
  longmemeval500_graph_embeddings
  longmemeval500_full_graphrag
)

stage_script() {
  case "$1" in
    phase81_full) printf '%s\n' "$repo_root/scripts/run_full_graphrag_979_resume.sh" ;;
    free128_graph_embeddings) printf '%s\n' "$repo_root/scripts/run_tg_free128_graph_embeddings.sh" ;;
    free128_full_graphrag) printf '%s\n' "$repo_root/scripts/run_tg_free128_full_graphrag.sh" ;;
    longmemeval500_graph_embeddings) printf '%s\n' "$repo_root/scripts/run_tg_longmemeval500_graph_embeddings_gpt4o.sh" ;;
    longmemeval500_full_graphrag) printf '%s\n' "$repo_root/scripts/run_tg_longmemeval500_full_graphrag_gpt4o.sh" ;;
    *) return 2 ;;
  esac
}

stage_output() {
  case "$1" in
    phase81_full) printf '%s\n' "$repo_root/results/raw/tg-phase81-full-graphrag-full-v2.json" ;;
    free128_graph_embeddings) printf '%s\n' "$repo_root/results/raw/tg-r32-free-language-graph-embeddings.json" ;;
    free128_full_graphrag) printf '%s\n' "$repo_root/results/raw/tg-r32-free-language-full-graphrag.json" ;;
    longmemeval500_graph_embeddings) printf '%s\n' "$repo_root/results/raw/tg-longmemeval-s-500-graph-embeddings-bridge81-gpt4o.json" ;;
    longmemeval500_full_graphrag) printf '%s\n' "$repo_root/results/raw/tg-longmemeval-s-500-full-graphrag-gpt4o.json" ;;
    *) return 2 ;;
  esac
}

known_start=0
for stage in "${stages[@]}"; do
  [[ "$stage" == "$start_at" ]] && known_start=1
done
[[ $known_start -eq 1 ]] || { printf 'Unknown start stage: %s\n' "$start_at" >&2; exit 2; }

if [[ -f "$env_file" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
fi

errors=0
printf '%s\n' 'TrustGraph final-suite preflight'
token_file="${PMSB_TG_TOKEN_FILE:-/tmp/pmsb-fullgraphrag-token-v2}"
if [[ ! -r "$token_file" ]]; then
  printf '  MISSING TrustGraph token file: %s\n' "$token_file"
  errors=$((errors + 1))
fi
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  printf '%s\n' '  MISSING OPENAI_API_KEY (required by paired GPT-4o reader and official judge)'
  errors=$((errors + 1))
fi
required_files=(
  "$repo_root/.venv/bin/python"
  /home/felipe/dev/ai/gitlab/ASM/data/longmemeval/longmemeval_s_cleaned.json
  /home/felipe/dev/ai/gitlab/ASM/data/longmemeval/longmemeval_oracle.json
  /home/felipe/dev/ai/gitlab/LongMemEval/.venv/bin/python
  /home/felipe/dev/ai/gitlab/LongMemEval/src/evaluation/evaluate_qa.py
  /home/felipe/dev/ai/gitlab/asm-memory-bridge/runs/dual_asm_r32/results.json
  /home/felipe/dev/ai/gitlab/asm-memory-bridge/runs/asm_bridge81_longmemeval_gpt4o/results.json
)
for required in "${required_files[@]}"; do
  if [[ ! -e "$required" ]]; then
    printf '  MISSING required path: %s\n' "$required"
    errors=$((errors + 1))
  fi
done
for stage in "${stages[@]}"; do
  runner="$(stage_script "$stage")"
  output="$(stage_output "$stage")"
  if [[ -x "$runner" ]]; then
    printf '  READY   %-40s %s\n' "$stage" "$runner"
  else
    printf '  MISSING %-40s %s\n' "$stage" "$runner"
    errors=$((errors + 1))
  fi
  printf '           output: %s\n' "$output"
done

if [[ $errors -gt 0 ]]; then
  printf '\nRefusing to start: %d stage runner(s) are absent or not executable.\n' "$errors" >&2
  exit 3
fi
[[ $preflight_only -eq 0 ]] || exit 0
[[ $dry_run -eq 0 ]] || { printf '%s\n' 'Dry run complete; no stage executed.'; exit 0; }

if ! mkdir "$lock_dir" 2>/dev/null; then
  printf 'Another final suite owns the lock: %s\n' "$lock_dir" >&2
  exit 4
fi
cleanup() {
  if [[ $text_completion_switched -eq 1 ]]; then
    "$repo_root/scripts/switch_trustgraph_text_completion.sh" ollama || true
  fi
  rmdir "$lock_dir" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
mkdir -p "$log_root"

started=0
for stage in "${stages[@]}"; do
  if [[ $started -eq 0 ]]; then
    [[ "$stage" == "$start_at" ]] || continue
    started=1
  fi
  if [[ "$stage" == "longmemeval500_full_graphrag" ]]; then
    printf '\n[%s] switching TrustGraph text-completion workers to OpenAI GPT-4o\n' \
      "$(date --iso-8601=seconds)" | tee -a "$log_root/${stage}.log"
    "$repo_root/scripts/switch_trustgraph_text_completion.sh" openai
    text_completion_switched=1
  fi
  runner="$(stage_script "$stage")"
  log="$log_root/${stage}.log"
  printf '\n[%s] starting %s\n' "$(date --iso-8601=seconds)" "$stage" | tee -a "$log"
  "$runner" 2>&1 | tee -a "$log"
  printf '[%s] completed %s\n' "$(date --iso-8601=seconds)" "$stage" | tee -a "$log"
done

PYTHONPATH="$repo_root/src" python -m persistent_memory_scaling.finalization \
  --config "$repo_root/configs/finalization.json" \
  --json "$repo_root/manifests/finalization-status.json" \
  --markdown "$repo_root/docs/report/013_finalization_status.md"
