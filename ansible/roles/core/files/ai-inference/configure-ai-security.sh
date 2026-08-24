#!/usr/bin/env bash
# UFW hardening, Docker daemon iptables, localhost-only exposure policy
set -euo pipefail

log() { echo "[configure-ai-security] $*"; }

log "Configuring Docker daemon.json (iptables integration — prevent UFW bypass)"
install -d -m 755 /etc/docker
cat >/etc/docker/daemon.json <<'EOF'
{
  "iptables": true,
  "ip6tables": true,
  "live-restore": true,
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF
systemctl restart docker || true

log "UFW: allow SSH and HTTPS; deny AI engine ports from public"
ufw --force enable || true
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'OpenSSH'
ufw allow 443/tcp comment 'CoreNova AI HTTPS'
ufw deny 8080/tcp comment 'Open WebUI localhost only'
ufw deny 11434/tcp comment 'Ollama localhost only'
ufw deny 8000/tcp comment 'vLLM localhost only'

log "Security configuration complete"
