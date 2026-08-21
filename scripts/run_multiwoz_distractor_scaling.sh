#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

asm_root="$(realpath "${ASM_ROOT:-../ASM}")"
bridge_root="$(realpath "${ASM_BRIDGE_ROOT:-../asm-memory-bridge}")"
multiwoz_root="$(realpath "${MULTIWOZ_ROOT:-../MultiWOZ}")"
python_bin="${PYTHON_BIN:-$asm_root/.venv/bin/python}"
reader_config="${READER_CONFIG:-configs/asm-memory-bridge/qwen3-14b-local-reader.json}"
run_root="${RUN_ROOT:-results/raw/paired-multiwoz-distractors-qwen3-14b}"
distractors="${DISTRACTORS:-0,100,1000}"
queries="${QUERIES:-20}"

checkpoint="${ASM_CHECKPOINT:-$asm_root/runs/asm_cm_language_improvement_10m_seed1/asm_cm/seed_1/training/checkpoint_final.pt}"
artifact="${ASM_ARTIFACT:-$bridge_root/runs/asm_cm_phase76_multiwoz_commercial/seed_1/multiwoz_commercial_address_head.pt}"
phase8_results="${PHASE8_RESULTS:-$bridge_root/runs/asm_memory_bridge_phase8_qwen35/results.json}"

largest="${distractors##*,}"
largest="${largest//[[:space:]]/}"
if [[ "$largest" -gt 1000 && "${ALLOW_LONG_RUN:-0}" != "1" ]]; then
  echo "Refusing an unacknowledged long ASM run through $largest distractors." >&2
  echo "Run the pilot first, or set ALLOW_LONG_RUN=1 after reviewing runtime." >&2
  exit 2
fi

export PYTHONPATH="$repo_root/src:$bridge_root/src:$bridge_root:$asm_root/src${PYTHONPATH:+:$PYTHONPATH}"

exec "$python_bin" -m persistent_memory_scaling.multiwoz_paired_runner \
  --distractors "$distractors" \
  --queries "$queries" \
  --top-k-values "${TOP_K_VALUES:-5,10,20}" \
  --quality-recall-floor "${QUALITY_RECALL_FLOOR:-0.90}" \
  --quality-qa-floor "${QUALITY_QA_FLOOR:-0.65}" \
  --chunk-size "${CHUNK_SIZE:-10}" \
  --capacity "${CAPACITY:-1024}" \
  --compact-max-total-bytes "${COMPACT_MAX_TOTAL_BYTES:-6144}" \
  --compact-max-bytes-per-memory "${COMPACT_MAX_BYTES_PER_MEMORY:-1536}" \
  --compact-max-anchors-per-memory "${COMPACT_MAX_ANCHORS_PER_MEMORY:-6}" \
  --compact-window-radius "${COMPACT_WINDOW_RADIUS:-2}" \
  --checkpoint "$checkpoint" \
  --artifact "$artifact" \
  --asm-source-root "$asm_root" \
  --bridge-source-root "$bridge_root" \
  --multiwoz-root "$multiwoz_root" \
  --phase8-results "$phase8_results" \
  --reader-config "$reader_config" \
  --device "${DEVICE:-cuda}" \
  --output-root "$run_root"
