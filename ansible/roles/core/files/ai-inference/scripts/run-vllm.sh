#!/usr/bin/env bash
# Start vLLM with dynamic tensor-parallel-size from GPU count
set -euo pipefail

COMPOSE_DIR="/opt/corenova/ai/compose"
cd "$COMPOSE_DIR"

log() { echo "[run-vllm] $*"; }

if ! command -v nvidia-smi >/dev/null 2>&1; then
  log "ERROR: nvidia-smi not found — launch on a GPU instance"
  exit 1
fi

GPU_COUNT=$(nvidia-smi -L 2>/dev/null | wc -l | tr -d ' ')
if [ "${GPU_COUNT}" -lt 1 ]; then
  GPU_COUNT=1
fi

log "Detected ${GPU_COUNT} GPU(s) — tensor-parallel-size=${GPU_COUNT}"
export VLLM_TENSOR_PARALLEL_SIZE="${GPU_COUNT}"

# shellcheck disable=SC1091
[ -f "${COMPOSE_DIR}/.env" ] && set -a && source "${COMPOSE_DIR}/.env" && set +a

exec /usr/bin/docker compose --profile vllm up -d vllm
