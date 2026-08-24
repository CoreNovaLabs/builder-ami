#!/usr/bin/env bash
# Install cloud-init drop-in and ensure first-boot bootstrap paths exist
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_ROOT="/opt/corenova/ai"

log() { echo "[install-cloud-init-bootstrap] $*"; }

log "Installing cloud-init configuration"
install -d -m 755 /etc/cloud/cloud.cfg.d
install -m 644 "${INSTALL_ROOT}/cloud-init/99-corenova-ai.cfg" /etc/cloud/cloud.cfg.d/99-corenova-ai.cfg

log "Ensuring runtime state directories"
install -d -m 755 /var/lib/corenova

log "Regenerate SSH host keys on first boot if missing (Marketplace scrub removes them)"
cat >/etc/systemd/system/corenova-ssh-hostkeys.service <<'EOF'
[Unit]
Description=Regenerate SSH host keys if missing after AMI scrub
DefaultDependencies=no
ConditionPathExists=!/etc/ssh/ssh_host_rsa_key
After=local-fs.target
Before=ssh.service sshd.service
Conflicts=shutdown.target

[Service]
Type=oneshot
ExecStart=/usr/bin/ssh-keygen -A
RemainAfterExit=yes

[Install]
RequiredBy=ssh.service
EOF
systemctl enable corenova-ssh-hostkeys.service

log "cloud-init bootstrap install complete"
