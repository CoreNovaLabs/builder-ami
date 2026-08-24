#!/usr/bin/env bash
# Marketplace pre-snapshot scrub — extends GPU Base cleanup with AI-specific hygiene
set -euo pipefail

log() { echo "[cleanup-scrub] $*"; }

log "Removing pre-baked authorized_keys (ubuntu, root)"
rm -f /home/ubuntu/.ssh/authorized_keys
rm -f /root/.ssh/authorized_keys
find / -xdev -name 'authorized_keys' -type f -delete 2>/dev/null || true

log "Removing AWS credentials and shell history"
rm -f /root/.aws/credentials /root/.aws/config
rm -f /home/ubuntu/.aws/credentials /home/ubuntu/.aws/config
truncate -s 0 /root/.bash_history /home/ubuntu/.bash_history 2>/dev/null || true
rm -f /root/.lesshst /home/ubuntu/.lesshst 2>/dev/null || true

log "Clearing test model artifacts and tokens"
rm -rf /root/.ollama /home/ubuntu/.ollama
rm -rf /mnt/models/ollama/* /mnt/models/vllm/* 2>/dev/null || true
rm -f /root/.cache/huggingface/token /home/ubuntu/.cache/huggingface/token 2>/dev/null || true
rm -rf /var/lib/corenova/admin-bootstrapped /var/lib/corenova/models-volume-ready /var/lib/corenova/docker-gpu-ready /var/lib/corenova/default-model-pulled 2>/dev/null || true
rm -f /opt/corenova/ai/compose/.env

log "Resetting SSH host keys (regenerated on buyer first boot)"
rm -f /etc/ssh/ssh_host_*_key /etc/ssh/ssh_host_*_key.pub

log "Verifying Docker daemon iptables integration"
if [ -f /etc/docker/daemon.json ]; then
  grep -q '"iptables"[[:space:]]*:[[:space:]]*true' /etc/docker/daemon.json \
    || log "WARN: daemon.json missing iptables:true"
else
  log "WARN: /etc/docker/daemon.json missing"
fi

log "Stopping Docker containers before snapshot"
systemctl stop nginx 2>/dev/null || true
if [ -d /opt/corenova/ai/compose ]; then
  (cd /opt/corenova/ai/compose && docker compose down 2>/dev/null) || true
fi
systemctl stop docker 2>/dev/null || true

log "Cleanup scrub complete"
