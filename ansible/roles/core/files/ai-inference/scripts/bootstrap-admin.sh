#!/usr/bin/env bash
# Seed Open WebUI admin from EC2 Instance ID (IMDS) — prevents public signup race
set -euo pipefail

COMPOSE_DIR="/opt/corenova/ai/compose"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@local.host}"
IMDS_BASE="http://169.254.169.254/latest"
MARKER="/var/lib/corenova/admin-bootstrapped"

log() { echo "[bootstrap-admin] $*"; }

if [ -f "$MARKER" ]; then
  log "Admin already bootstrapped"
  exit 0
fi

log "Fetching Instance ID from IMDS"
TOKEN=$(curl -sf -X PUT "${IMDS_BASE}/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" || true)
if [ -n "$TOKEN" ]; then
  INSTANCE_ID=$(curl -sf -H "X-aws-ec2-metadata-token: ${TOKEN}" "${IMDS_BASE}/meta-data/instance-id")
else
  INSTANCE_ID=$(curl -sf "${IMDS_BASE}/meta-data/instance-id")
fi

if [ -z "$INSTANCE_ID" ]; then
  log "WARN: Could not read instance-id (non-EC2 build?) — using build-time placeholder"
  INSTANCE_ID="i-local-build-placeholder"
fi

log "Writing runtime .env (admin password = instance id)"
install -d -m 755 /var/lib/corenova
WEBUI_SECRET=$(openssl rand -hex 32)
DEFAULT_OLLAMA_MODEL="${DEFAULT_OLLAMA_MODEL:-qwen3:0.6b}"
cat >"${COMPOSE_DIR}/.env" <<EOF
# Generated at first boot — do not commit
WEBUI_SECRET_KEY=${WEBUI_SECRET}
WEBUI_AUTH=true
ENABLE_SIGNUP=false
WEBUI_ADMIN_EMAIL=${ADMIN_EMAIL}
WEBUI_ADMIN_PASSWORD=${INSTANCE_ID}
OLLAMA_BASE_URL=http://127.0.0.1:11434
OPENAI_API_BASE_URL=http://127.0.0.1:8000/v1
OLLAMA_MODELS=/mnt/models/ollama
HF_HOME=/mnt/models/vllm/huggingface
DEFAULT_OLLAMA_MODEL=${DEFAULT_OLLAMA_MODEL}
DEFAULT_MODELS=${DEFAULT_OLLAMA_MODEL}
EOF
chmod 640 "${COMPOSE_DIR}/.env"

log "Starting Ollama"
cd "$COMPOSE_DIR"
/usr/bin/docker compose up -d ollama

log "Pulling default chat model on first boot"
/opt/corenova/ai/scripts/pull-default-model.sh || true

log "Starting Open WebUI"
/usr/bin/docker compose up -d open-webui

log "Waiting for Open WebUI (up to 120s)"
for i in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:8080/health" >/dev/null 2>&1 \
    || curl -sf "http://127.0.0.1:8080/" >/dev/null 2>&1; then
    log "Open WebUI responding"
    break
  fi
  sleep 2
  if [ "$i" -eq 60 ]; then
    log "WARN: Open WebUI did not respond in time — admin may need manual recovery"
    exit 0
  fi
done

log "Verifying admin login endpoint"
if curl -sf -X POST "http://127.0.0.1:8080/api/v1/auths/signin" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${INSTANCE_ID}\"}" >/dev/null 2>&1; then
  log "Admin signin OK for ${ADMIN_EMAIL}"
else
  log "Admin signin not yet available — WEBUI_ADMIN_* env should seed on first container init"
fi

touch "$MARKER"
log "Bootstrap complete — change password after first login"
