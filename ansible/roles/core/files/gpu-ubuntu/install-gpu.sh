#!/usr/bin/env bash
# Install NVIDIA Driver + CUDA Toolkit on Ubuntu 22.04 (CUDA repo)
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

CUDA_TOOLKIT_VERSION="${CUDA_TOOLKIT_VERSION:-12-4}"
DRIVER_PACKAGE="${DRIVER_PACKAGE:-cuda-drivers-550}"
CUDA_KEYRING_URL="${CUDA_KEYRING_URL:-https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb}"

log() { echo "[install-gpu] $*"; }

log "Installing DKMS prerequisites"
apt-get update -y
apt-get -y install \
  build-essential \
  dkms \
  "linux-headers-$(uname -r)" \
  wget

log "Blacklisting nouveau"
cat >/etc/modprobe.d/blacklist-nouveau.conf <<'EOF'
blacklist nouveau
options nouveau modeset=0
EOF
update-initramfs -u || true

log "Adding NVIDIA CUDA repository (Ubuntu 22.04)"
KEYRING_DEB="/tmp/cuda-keyring.deb"
wget -q -O "$KEYRING_DEB" "$CUDA_KEYRING_URL"
dpkg -i "$KEYRING_DEB"
rm -f "$KEYRING_DEB"
apt-get update -y

log "Installing ${DRIVER_PACKAGE}, cuda-compiler-${CUDA_TOOLKIT_VERSION}, cuda-libraries-${CUDA_TOOLKIT_VERSION}"
apt-get -y install \
  "$DRIVER_PACKAGE" \
  "cuda-compiler-${CUDA_TOOLKIT_VERSION}" \
  "cuda-libraries-${CUDA_TOOLKIT_VERSION}"

log "Persist CUDA environment for login shells"
cat >/etc/profile.d/cuda.sh <<'EOF'
export PATH=/usr/local/cuda/bin${PATH:+:${PATH}}
export LD_LIBRARY_PATH=/usr/local/cuda/lib64${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}
EOF
chmod 644 /etc/profile.d/cuda.sh

if [ -L /usr/local/cuda ] || [ -d /usr/local/cuda ]; then
  log "CUDA symlink: $(readlink -f /usr/local/cuda || echo /usr/local/cuda)"
fi

log "GPU stack packages installed (AIDE update skipped — CUDA tree too large for build-time scan)"
