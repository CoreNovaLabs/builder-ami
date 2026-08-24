#!/usr/bin/env bash
# Configure Docker NVIDIA runtime on first GPU boot (Packer builds on non-GPU omit runtime)
set -euo pipefail

MARKER="/var/lib/corenova/docker-gpu-ready"

log() { echo "[configure-docker-gpu] $*"; }

needs_configure() {
  [ ! -f /etc/docker/daemon.json ] && return 0
  grep -q '"nvidia"' /etc/docker/daemon.json 2>/dev/null || return 0
  return 1
}

if [ -f "$MARKER" ] && ! needs_configure; then
  log "NVIDIA Docker runtime already configured"
  exit 0
fi

log "Waiting for NVIDIA driver (up to 120s)"
gpu_ready=0
for _ in $(seq 1 60); do
  if nvidia-smi -L >/dev/null 2>&1; then
    gpu_ready=1
    break
  fi
  sleep 2
done

if [ "$gpu_ready" -ne 1 ]; then
  log "No GPU detected — skipping NVIDIA runtime configure"
  exit 0
fi

log "Configuring Docker NVIDIA runtime"
nvidia-ctk runtime configure --runtime=docker

if systemctl is-active --quiet docker; then
  log "Restarting Docker to apply NVIDIA runtime"
  systemctl restart docker
fi

install -d -m 755 /var/lib/corenova
touch "$MARKER"
log "Docker GPU runtime ready"
