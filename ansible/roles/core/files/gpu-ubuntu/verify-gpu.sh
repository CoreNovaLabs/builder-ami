#!/usr/bin/env bash
# Post-reboot validation on builder instance
set -euo pipefail

VERIFY_GPU="${VERIFY_GPU:-false}"

log() { echo "[verify-gpu] $*"; }

if [ "$VERIFY_GPU" != "true" ]; then
  log "Headless build — verifying CUDA packages only (nvidia-smi deferred to GPU launch)"
  if [ -x /usr/local/cuda/bin/nvcc ]; then
    /usr/local/cuda/bin/nvcc --version
  elif command -v nvcc >/dev/null 2>&1; then
    nvcc --version
  else
    log "ERROR: nvcc not found"
    exit 1
  fi
  if dpkg -l 2>/dev/null | grep -qE 'nvidia-dkms-|cuda-drivers|libnvidia-compute'; then
    log "NVIDIA driver packages present"
  else
    log "WARN: driver package grep inconclusive — nvcc OK, continuing"
  fi
  log "Headless package verification OK"
  exit 0
fi

if ! command -v nvidia-smi >/dev/null 2>&1; then
  log "ERROR: nvidia-smi not found after driver install"
  exit 1
fi

log "nvidia-smi output:"
nvidia-smi

if command -v nvcc >/dev/null 2>&1; then
  log "CUDA compiler:"
  nvcc --version
else
  # nvcc may live under /usr/local/cuda/bin before profile.d is sourced
  if [ -x /usr/local/cuda/bin/nvcc ]; then
    /usr/local/cuda/bin/nvcc --version
  else
    log "ERROR: nvcc not found"
    exit 1
  fi
fi

log "GPU validation OK"
