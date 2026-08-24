#!/usr/bin/env bash
set -euo pipefail

PRODUCT_KEY="${1:?usage: scripts/smoke_test_ami.sh <product-key> <ami-id>}"
AMI_ID="${2:?usage: scripts/smoke_test_ami.sh <product-key> <ami-id>}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source scripts/lib/aws_identity.sh

assert_corenova_assumed_role CoreNovaAmiBuilderRole

if [[ -x .venv/bin/python ]]; then
  DEFAULT_PYTHON=".venv/bin/python"
else
  DEFAULT_PYTHON="python3"
fi
PYTHON="${PYTHON:-$DEFAULT_PYTHON}"

REGION="$("$PYTHON" - <<PY
import sys
sys.path.insert(0, "scripts")
from productlib import product_by_key
p = product_by_key("$PRODUCT_KEY")
print(p["_aws"]["region"])
PY
)"
SSH_USER="$("$PYTHON" - <<PY
import sys
sys.path.insert(0, "scripts")
from productlib import product_by_key
p = product_by_key("$PRODUCT_KEY")
print(p["ssh_username"])
PY
)"
INSTANCE_TYPE="$("$PYTHON" - <<PY
import sys
sys.path.insert(0, "scripts")
from productlib import product_by_key
p = product_by_key("$PRODUCT_KEY")
print(p["recommended_instance_type"])
PY
)"
OS_NAME="$("$PYTHON" - <<PY
import sys
sys.path.insert(0, "scripts")
from productlib import product_by_key
p = product_by_key("$PRODUCT_KEY")
print(p["operating_system_name"])
PY
)"
PROFILE="$("$PYTHON" - <<PY
import sys
sys.path.insert(0, "scripts")
from productlib import product_by_key
p = product_by_key("$PRODUCT_KEY")
print(p.get("profile", "hardened-linux"))
PY
)"

STAMP="$(date -u +%Y%m%d%H%M%S)"
KEY_NAME="builder-ami-smoke-${PRODUCT_KEY}-${STAMP}"
KEY_FILE="build/${KEY_NAME}.pem"
SG_NAME="builder-ami-smoke-${PRODUCT_KEY}-${STAMP}"
INSTANCE_ID=""
SG_ID=""

cleanup() {
  set +e
  if [[ -n "$INSTANCE_ID" ]]; then
    aws ec2 terminate-instances --region "$REGION" --instance-ids "$INSTANCE_ID" >/dev/null
    aws ec2 wait instance-terminated --region "$REGION" --instance-ids "$INSTANCE_ID"
  fi
  if [[ -n "$SG_ID" ]]; then
    aws ec2 delete-security-group --region "$REGION" --group-id "$SG_ID" >/dev/null
  fi
  aws ec2 delete-key-pair --region "$REGION" --key-name "$KEY_NAME" >/dev/null 2>&1
  rm -f "$KEY_FILE"
}
trap cleanup EXIT

mkdir -p build logs
aws ec2 create-key-pair \
  --region "$REGION" \
  --key-name "$KEY_NAME" \
  --tag-specifications "ResourceType=key-pair,Tags=[{Key=Name,Value=${KEY_NAME}},{Key=Project,Value=builder-ami},{Key=ProductKey,Value=${PRODUCT_KEY}},{Key=Purpose,Value=ssh-smoke-test}]" \
  --query KeyMaterial \
  --output text > "$KEY_FILE"
chmod 0600 "$KEY_FILE"

DEFAULT_VPC_ID="$(aws ec2 describe-vpcs --region "$REGION" --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId' --output text)"
SG_ID="$(aws ec2 create-security-group \
  --region "$REGION" \
  --group-name "$SG_NAME" \
  --description "$SG_NAME" \
  --vpc-id "$DEFAULT_VPC_ID" \
  --tag-specifications "ResourceType=security-group,Tags=[{Key=Name,Value=${SG_NAME}},{Key=Project,Value=builder-ami},{Key=ProductKey,Value=${PRODUCT_KEY}},{Key=Purpose,Value=ssh-smoke-test}]" \
  --query GroupId \
  --output text)"
MY_IP="$(curl -fsSL https://checkip.amazonaws.com)/32"
aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$SG_ID" --ip-permissions "IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges=[{CidrIp=${MY_IP},Description=builder-ami-smoke}]" >/dev/null

INSTANCE_ID="$(aws ec2 run-instances \
  --region "$REGION" \
  --image-id "$AMI_ID" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=1 \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${SG_NAME}},{Key=Project,Value=builder-ami},{Key=ProductKey,Value=${PRODUCT_KEY}},{Key=Purpose,Value=smoke-test}]" \
    "ResourceType=volume,Tags=[{Key=Name,Value=${SG_NAME}},{Key=Project,Value=builder-ami},{Key=ProductKey,Value=${PRODUCT_KEY}},{Key=Purpose,Value=smoke-test}]" \
  --query 'Instances[0].InstanceId' \
  --output text)"

aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"
PUBLIC_IP="$(aws ec2 describe-instances --region "$REGION" --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)"

SSH_OPTS=(-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o IdentitiesOnly=yes -o ConnectTimeout=10 -i "$KEY_FILE")
for _ in $(seq 1 30); do
  if ssh "${SSH_OPTS[@]}" "${SSH_USER}@${PUBLIC_IP}" "true" >/dev/null 2>&1; then
    break
  fi
  sleep 10
done

ssh "${SSH_OPTS[@]}" "${SSH_USER}@${PUBLIC_IP}" 'cloud-init status --wait || true'
if [[ "$OS_NAME" == "DEBIAN" || "$OS_NAME" == "UBUNTU" ]]; then
  ssh "${SSH_OPTS[@]}" "${SSH_USER}@${PUBLIC_IP}" 'set -eux; uname -m; sudo sshd -T | grep -E "permitrootlogin|passwordauthentication"; systemctl is-active rsyslog; sudo systemctl is-active ufw; sudo systemctl is-active chrony; sudo systemctl is-enabled unattended-upgrades || true'
else
  ssh "${SSH_OPTS[@]}" "${SSH_USER}@${PUBLIC_IP}" 'set -eux; uname -m; sudo sshd -T | grep -E "permitrootlogin|passwordauthentication"; systemctl is-active rsyslog; sudo systemctl is-active firewalld; sudo systemctl is-active chronyd; sudo systemctl is-enabled dnf-automatic.timer || true'
fi

# GPU profiles launch on a GPU instance type, so the DKMS modules must load
# and expose the adapter without any manual step.
if [[ "$PROFILE" == "gpu-ubuntu" || "$PROFILE" == "ai-inference" ]]; then
  ssh "${SSH_OPTS[@]}" "${SSH_USER}@${PUBLIC_IP}" 'set -eux; nvidia-smi -L; nvidia-smi --query-gpu=driver_version --format=csv,noheader'
fi

# The AI stack is a oneshot unit whose first boot pulls container images, so
# poll it instead of failing immediately.
if [[ "$PROFILE" == "ai-inference" ]]; then
  ssh "${SSH_OPTS[@]}" "${SSH_USER}@${PUBLIC_IP}" 'set -eux; sudo systemctl is-active docker; systemctl is-enabled corenova-docker-gpu.service setup-models-volume.service corenova-bootstrap-admin.service corenova-ai-stack.service nginx.service'
  STACK_STATE=""
  for _ in $(seq 1 60); do
    STACK_STATE="$(ssh "${SSH_OPTS[@]}" "${SSH_USER}@${PUBLIC_IP}" 'systemctl is-active corenova-ai-stack.service' 2>/dev/null || true)"
    if [[ "$STACK_STATE" == "active" ]]; then
      break
    fi
    sleep 10
  done
  if [[ "$STACK_STATE" != "active" ]]; then
    ssh "${SSH_OPTS[@]}" "${SSH_USER}@${PUBLIC_IP}" 'sudo systemctl status corenova-ai-stack.service --no-pager -l || true; sudo journalctl -u corenova-ai-stack.service --no-pager -n 100 || true' >&2 || true
    echo "ERROR: corenova-ai-stack.service did not become active (state: ${STACK_STATE})" >&2
    exit 1
  fi
  ssh "${SSH_OPTS[@]}" "${SSH_USER}@${PUBLIC_IP}" 'set -eux; sudo docker ps --format "{{.Names}}"; sudo docker ps --format "{{.Names}}" | grep -x corenova-ollama; sudo docker ps --format "{{.Names}}" | grep -x corenova-open-webui; systemctl is-active nginx'
fi

echo "SMOKE_OK ${PRODUCT_KEY} ${AMI_ID} ${INSTANCE_ID}"
