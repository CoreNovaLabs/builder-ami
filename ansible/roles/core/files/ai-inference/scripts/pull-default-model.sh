#!/usr/bin/env bash
# Pull default Ollama model on first boot (after Ollama container is running)
set -euo pipefail

DEFAULT_MODEL="${DEFAULT_OLLAMA_MODEL:-qwen3:0.6b}"
MARKER="/var/lib/corenova/default-model-pulled"
CONTAINER="${OLLAMA_CONTAINER:-corenova-ollama}"

log() { echo "[pull-default-model] $*"; }

if [ -f "$MARKER" ]; then
  log "Default model already pulled"
  exit 0
fi

log "Waiting for Ollama API (up to 180s)"
ready=0
for _ in $(seq 1 90); do
  if /usr/bin/docker exec "$CONTAINER" ollama list >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done

if [ "$ready" -ne 1 ]; then
  log "WARN: Ollama not ready — skip default model pull"
  exit 0
fi

log "Pulling default Ollama model: ${DEFAULT_MODEL}"
if /usr/bin/docker exec "$CONTAINER" ollama pull "$DEFAULT_MODEL"; then
  install -d -m 755 /var/lib/corenova
  touch "$MARKER"
  log "Default model ready: ${DEFAULT_MODEL}"
else
  log "WARN: Failed to pull ${DEFAULT_MODEL} — pull manually: docker exec ${CONTAINER} ollama pull ${DEFAULT_MODEL}"
  exit 0
fi
