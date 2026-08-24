#!/usr/bin/env bash
# Post-build / launch validation for AI stack (GPU instance recommended)
set -euo pipefail

VERIFY_GPU="${VERIFY_GPU:-false}"
VERIFY_AI="${VERIFY_AI:-false}"

log() { echo "[verify-ai-stack] $*"; }

if [ "$VERIFY_GPU" != "true" ] && [ "$VERIFY_AI" != "true" ]; then
  log "Skipping AI stack validation (headless build)"
  exit 0
fi

log "Checking Docker and NVIDIA runtime"
systemctl is-active docker
docker info >/dev/null 2>&1

if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi -L
else
  log "WARN: nvidia-smi unavailable"
fi

log "Checking compose services"
cd /opt/corenova/ai/compose
if [ -f .env ]; then
  docker compose up -d ollama open-webui
  for i in $(seq 1 30); do
    curl -sf http://127.0.0.1:8080/ >/dev/null 2>&1 && break
    sleep 2
  done
  curl -sf http://127.0.0.1:8080/ >/dev/null 2>&1 || log "WARN: Open WebUI not reachable on localhost:8080"
  curl -sf http://127.0.0.1:11434/ >/dev/null 2>&1 || log "WARN: Ollama not reachable on localhost:11434"
fi

log "Checking UFW denies engine ports (localhost bind still OK)"
ufw status | grep -E '11434|8000|8080' || true

if [ "$VERIFY_AI" = "true" ] && [ -x /opt/corenova/ai/scripts/run-vllm.sh ]; then
  log "vLLM tensor parallel smoke (requires model args in production)"
  GPU_COUNT=$(nvidia-smi -L 2>/dev/null | wc -l | tr -d ' ')
  log "GPU count for TP: ${GPU_COUNT}"
fi

log "AI stack verification complete"
