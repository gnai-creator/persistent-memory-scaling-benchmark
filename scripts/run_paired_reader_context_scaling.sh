#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

asm_root="$(realpath "${ASM_ROOT:-../ASM}")"
bridge_root="$(realpath "${ASM_BRIDGE_ROOT:-../asm-memory-bridge}")"
python_bin="${PYTHON_BIN:-$asm_root/.venv/bin/python}"
reader_config="${READER_CONFIG:-configs/asm-memory-bridge/qwen35-local-reader.json}"
run_root="${RUN_ROOT:-results/raw/paired-reader-context-scaling-qwen35}"
checkpoints="${CHECKPOINTS:-10000,100000,1000000}"
queries="${QUERIES:-1000}"

largest_checkpoint="${checkpoints##*,}"
if [[ "$largest_checkpoint" -gt 1000 && "${ALLOW_LONG_RUN:-0}" != "1" ]]; then
  echo "Refusing an unacknowledged long ASM run through $largest_checkpoint events." >&2
  echo "The measured scalar backend currently takes about 22-25 seconds/event." >&2
  echo "Run a smoke first, or set ALLOW_LONG_RUN=1 after reviewing the runtime estimate." >&2
  exit 2
fi

export PYTHONPATH="$repo_root/src:$bridge_root/src:$asm_root/src${PYTHONPATH:+:$PYTHONPATH}"

OUTPUT_ROOT="$run_root/asm" \
CHECKPOINTS="$checkpoints" \
QUERIES="$queries" \
ASM_ROOT="$asm_root" \
ASM_BRIDGE_ROOT="$bridge_root" \
PYTHON_BIN="$python_bin" \
READER_CONFIG="$reader_config" \
./scripts/run_asm_reader_context_scaling.sh

"$python_bin" -m persistent_memory_scaling.rag_reader_context_scaling_runner \
  --checkpoints "$checkpoints" \
  --queries "$queries" \
  --top-k 5 \
  --bridge-source-root "$bridge_root" \
  --reader-config "$reader_config" \
  --output-root "$run_root/rag"

"$python_bin" -m persistent_memory_scaling.paired_reader_context_scaling \
  --asm "$run_root/asm/reader-context.jsonl" \
  --rag "$run_root/rag/reader-context.jsonl" \
  --summary "$run_root/paired-summary.json" \
  --png "$run_root/asm-vs-rag.png" \
  --svg "$run_root/asm-vs-rag.svg"

printf 'Paired graph: %s\n' "$run_root/asm-vs-rag.png"
