#!/usr/bin/env bash
# Mount first non-root EBS volume to /mnt/models via AWS NVMe by-id symlinks
set -euo pipefail

MOUNT_POINT="${MOUNT_POINT:-/mnt/models}"
FSTAB_MARKER="# corenova-models-ebs"

log() { echo "[setup-models-volume] $*"; }

if mountpoint -q "$MOUNT_POINT"; then
  log "$MOUNT_POINT already mounted"
  exit 0
fi

install -d -m 755 "$MOUNT_POINT" /mnt/models/ollama /mnt/models/vllm

ROOT_SRC="$(findmnt -n -o SOURCE /)"
ROOT_DEV="$(readlink -f "$ROOT_SRC" | sed 's/p[0-9]*$//')"
log "Root block device baseline: $ROOT_DEV"

DATA_DEV=""
for id in /dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_vol*; do
  [ -e "$id" ] || continue
  dev="$(readlink -f "$id")"
  base_dev="$(echo "$dev" | sed 's/p[0-9]*$//')"
  if [[ "$base_dev" == "$ROOT_DEV" ]]; then
    log "Skipping root volume: $id -> $dev"
    continue
  fi
  if mount | grep -q "^${dev} "; then
    log "Skipping already mounted: $dev"
    continue
  fi
  DATA_DEV="$dev"
  log "Selected data volume: $id -> $dev"
  break
done

if [ -z "$DATA_DEV" ]; then
  log "No separate EBS data volume detected — using root filesystem under $MOUNT_POINT"
  chown -R ubuntu:ubuntu "$MOUNT_POINT" 2>/dev/null || true
  exit 0
fi

if ! blkid "$DATA_DEV" >/dev/null 2>&1; then
  log "Formatting $DATA_DEV as ext4"
  mkfs.ext4 -F "$DATA_DEV"
fi

UUID="$(blkid -s UUID -o value "$DATA_DEV")"
if ! grep -q "$FSTAB_MARKER" /etc/fstab; then
  echo "UUID=${UUID} ${MOUNT_POINT} ext4 defaults,nofail 0 2 ${FSTAB_MARKER}" >> /etc/fstab
fi

mount "$MOUNT_POINT" || mount "$DATA_DEV" "$MOUNT_POINT"
chown -R ubuntu:ubuntu "$MOUNT_POINT" 2>/dev/null || true
log "Mounted $DATA_DEV at $MOUNT_POINT (UUID=$UUID)"
