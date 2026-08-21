#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

asm_root="${ASM_ROOT:-../ASM}"
bridge_root="${ASM_BRIDGE_ROOT:-../asm-memory-bridge}"
asm_root="$(realpath "$asm_root")"
bridge_root="$(realpath "$bridge_root")"
python_bin="${PYTHON_BIN:-$asm_root/.venv/bin/python}"
checkpoint="${ASM_CHECKPOINT:-$asm_root/runs/asm_cm_language_improvement_10m_seed1/asm_cm/seed_1/training/checkpoint_final.pt}"
artifact="${ASM_ARTIFACT:-$bridge_root/runs/asm_cm_phase76_multiwoz_commercial/seed_1/multiwoz_commercial_address_head.pt}"
reader_config="${READER_CONFIG:-configs/asm-memory-bridge/qwen35-local-reader.json}"
output_root="${OUTPUT_ROOT:-results/raw/asm-reader-context-scaling-qwen35}"
checkpoints="${CHECKPOINTS:-10000,100000,1000000}"
queries="${QUERIES:-1000}"
device="${DEVICE:-auto}"
capacity="${CAPACITY:-1024}"
chunk_size="${CHUNK_SIZE:-1000}"

[[ -x "$python_bin" ]] || { echo "Python environment not found: $python_bin" >&2; exit 2; }
[[ -f "$checkpoint" ]] || { echo "ASM checkpoint not found: $checkpoint" >&2; exit 2; }
[[ -f "$artifact" ]] || { echo "Retrieval artifact not found: $artifact" >&2; exit 2; }
[[ -f "$reader_config" ]] || { echo "Reader config not found: $reader_config" >&2; exit 2; }
curl --fail --silent --show-error http://127.0.0.1:11434/api/tags >/dev/null || {
  echo "Local Ollama is unavailable at http://127.0.0.1:11434" >&2
  exit 2
}

export PYTHONPATH="$repo_root/src:$bridge_root/src:$asm_root/src${PYTHONPATH:+:$PYTHONPATH}"

exec "$python_bin" -m persistent_memory_scaling.asm_reader_context_scaling_runner \
  --checkpoints "$checkpoints" \
  --queries "$queries" \
  --chunk-size "$chunk_size" \
  --capacity "$capacity" \
  --checkpoint "$checkpoint" \
  --artifact "$artifact" \
  --asm-source-root "$asm_root" \
  --bridge-source-root "$bridge_root" \
  --reader-config "$reader_config" \
  --device "$device" \
  --output-root "$output_root"
