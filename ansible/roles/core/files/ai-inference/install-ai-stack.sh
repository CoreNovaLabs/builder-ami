#!/usr/bin/env bash
# Deploy AI stack files, systemd units, nginx TLS, CloudWatch Agent config
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

INSTALL_ROOT="/opt/corenova/ai"
DATA_ROOT="/var/lib/open-webui"

log() { echo "[install-ai-stack] $*"; }

log "Creating install directories"
install -d -m 755 "$INSTALL_ROOT"/{compose,scripts,config,certs,cloud-init}
install -d -m 755 /mnt/models/ollama /mnt/models/vllm
install -d -m 755 "$DATA_ROOT" /var/log/nginx /etc/corenova /var/lib/corenova

log "Compose assets expected at ${INSTALL_ROOT}/compose (provisioned by Packer)"
test -f "${INSTALL_ROOT}/compose/docker-compose.yml" || {
  log "FATAL: missing ${INSTALL_ROOT}/compose/docker-compose.yml"
  exit 1
}

log "Installing helper scripts"
SCRIPT_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER_SRC=""
for candidate in "${INSTALL_ROOT}/scripts" "${SCRIPT_SRC}"; do
  if [ -f "${candidate}/setup-models-volume.sh" ]; then
    HELPER_SRC="$candidate"
    break
  fi
done
if [ -z "$HELPER_SRC" ]; then
  log "FATAL: setup-models-volume.sh not found under ${INSTALL_ROOT}/scripts or ${SCRIPT_SRC}"
  exit 1
fi
if [ "$HELPER_SRC" != "${INSTALL_ROOT}/scripts" ]; then
  cp "${HELPER_SRC}/setup-models-volume.sh" "${HELPER_SRC}/bootstrap-admin.sh" \
    "${HELPER_SRC}/configure-docker-gpu.sh" "${HELPER_SRC}/pull-default-model.sh" "${HELPER_SRC}/run-vllm.sh" \
    "${INSTALL_ROOT}/scripts/"
fi
chmod +x "${INSTALL_ROOT}/scripts/"*.sh

log "Generating self-signed TLS certificate for nginx (buyer may replace)"
if [ ! -f "${INSTALL_ROOT}/certs/server.crt" ]; then
  openssl req -x509 -nodes -days 825 -newkey rsa:2048 \
    -keyout "${INSTALL_ROOT}/certs/server.key" \
    -out "${INSTALL_ROOT}/certs/server.crt" \
    -subj "/CN=corenova-ai-sandbox/O=CoreNova Intelligence Limited"
  chmod 600 "${INSTALL_ROOT}/certs/server.key"
fi

log "Installing CloudWatch Agent (enable on boot, no start during build)"
apt-get update -y
apt-get install -y nginx openssl wget
if ! dpkg -s amazon-cloudwatch-agent >/dev/null 2>&1; then
  CW_DEB="/tmp/amazon-cloudwatch-agent.deb"
  wget -q -O "$CW_DEB" https://amazoncloudwatch-agent.s3.amazonaws.com/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
  dpkg -i "$CW_DEB" || apt-get install -yf
  rm -f "$CW_DEB"
fi
if [ -f "${INSTALL_ROOT}/config/amazon-cloudwatch-agent.json" ]; then
  install -d -m 755 /opt/aws/amazon-cloudwatch-agent/etc
  install -m 644 "${INSTALL_ROOT}/config/amazon-cloudwatch-agent.json" \
    /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
  systemctl enable amazon-cloudwatch-agent
  systemctl stop amazon-cloudwatch-agent 2>/dev/null || true
fi

cat >/etc/corenova/ai-stack-readme.txt <<'EOF'
CoreNova Enterprise AI Inference Stack
- Attach IAM instance profile with CloudWatch logs permissions (see docs/public/iam-cloudwatch-minimal.json).
- First login: admin@local.host · password = EC2 Instance ID.
- Mount models EBS to /mnt/models (automatic on first boot when data volume attached).
EOF

log "Installing systemd units"
cat >/etc/systemd/system/corenova-docker-gpu.service <<'EOF'
[Unit]
Description=CoreNova configure Docker NVIDIA runtime on GPU instances
DefaultDependencies=no
After=docker.service network-online.target
Before=setup-models-volume.service corenova-bootstrap-admin.service corenova-ai-stack.service
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/opt/corenova/ai/scripts/configure-docker-gpu.sh

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/setup-models-volume.service <<'EOF'
[Unit]
Description=CoreNova mount EBS models volume by-id
DefaultDependencies=no
After=local-fs.target cloud-init.service corenova-docker-gpu.service
Before=corenova-bootstrap-admin.service corenova-ai-stack.service
ConditionPathExists=!/var/lib/corenova/models-volume-ready

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/opt/corenova/ai/scripts/setup-models-volume.sh
ExecStartPost=/usr/bin/touch /var/lib/corenova/models-volume-ready

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/corenova-bootstrap-admin.service <<'EOF'
[Unit]
Description=CoreNova seed Open WebUI admin from Instance ID
After=corenova-docker-gpu.service setup-models-volume.service docker.service network-online.target
Before=corenova-ai-stack.service nginx.service
Requires=corenova-docker-gpu.service
Wants=network-online.target
ConditionPathExists=!/var/lib/corenova/admin-bootstrapped

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/opt/corenova/ai/scripts/bootstrap-admin.sh

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/corenova-ai-stack.service <<'EOF'
[Unit]
Description=CoreNova AI stack (Ollama + Open WebUI + optional vLLM)
After=corenova-bootstrap-admin.service docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/corenova/ai/compose
EnvironmentFile=-/opt/corenova/ai/compose/.env
ExecStart=/usr/bin/docker compose up -d ollama open-webui
ExecStop=/usr/bin/docker compose stop

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/corenova-ai-vllm.service <<'EOF'
[Unit]
Description=CoreNova vLLM engine (optional profile)
After=corenova-ai-stack.service docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/corenova/ai/compose
EnvironmentFile=-/opt/corenova/ai/compose/.env
ExecStart=/opt/corenova/ai/scripts/run-vllm.sh
ExecStop=/usr/bin/docker compose --profile vllm stop vllm

[Install]
WantedBy=multi-user.target
EOF

install -d -m 755 /etc/systemd/system/nginx.service.d
cat >/etc/systemd/system/nginx.service.d/corenova-ai.conf <<'EOF'
[Unit]
After=corenova-ai-stack.service
Requires=corenova-ai-stack.service
EOF

log "Installing nginx site"
rm -f /etc/nginx/sites-enabled/default
cp "${INSTALL_ROOT}/compose/nginx/default.conf" /etc/nginx/sites-available/corenova-ai
ln -sf /etc/nginx/sites-available/corenova-ai /etc/nginx/sites-enabled/corenova-ai

log "Static .env template (runtime .env written by bootstrap-admin on first boot)"
cp "${INSTALL_ROOT}/compose/.env.example" "${INSTALL_ROOT}/compose/.env"
chmod 640 "${INSTALL_ROOT}/compose/.env"

systemctl daemon-reload
systemctl enable corenova-docker-gpu.service setup-models-volume.service corenova-bootstrap-admin.service corenova-ai-stack.service nginx.service

log "AI stack install complete"
