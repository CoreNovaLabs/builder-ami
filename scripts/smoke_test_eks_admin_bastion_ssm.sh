#!/usr/bin/env bash
set -euo pipefail

PRODUCT_KEY="${1:?usage: scripts/smoke_test_eks_admin_bastion_ssm.sh <product-key> <ami-id>}"
AMI_ID="${2:?usage: scripts/smoke_test_eks_admin_bastion_ssm.sh <product-key> <ami-id>}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source scripts/lib/aws_identity.sh

assert_corenova_assumed_role CoreNovaEksBastionSmokeRunnerRole

if [[ -x .venv/bin/python ]]; then
  DEFAULT_PYTHON=".venv/bin/python"
else
  DEFAULT_PYTHON="python3"
fi
PYTHON="${PYTHON:-$DEFAULT_PYTHON}"

: "${CORENOVA_SMOKE_SUBNET_ID:?set CORENOVA_SMOKE_SUBNET_ID to the reviewed smoke subnet}"
: "${CORENOVA_SMOKE_INSTANCE_PROFILE_NAME:?set CORENOVA_SMOKE_INSTANCE_PROFILE_NAME to the dedicated CoreNova smoke instance profile}"

ALLOW_PUBLIC_IP="${CORENOVA_SMOKE_ALLOW_PUBLIC_IP:-false}"
if [[ "$ALLOW_PUBLIC_IP" != "true" && "$ALLOW_PUBLIC_IP" != "false" ]]; then
  echo "CORENOVA_SMOKE_ALLOW_PUBLIC_IP must be true or false" >&2
  exit 2
fi

export CORENOVA_PRODUCTS_FILE="${CORENOVA_PRODUCTS_FILE:-products.candidates.yaml}"

read_product_field() {
  "$PYTHON" - "$PRODUCT_KEY" "$1" <<'PY'
import sys

sys.path.insert(0, "scripts")
from productlib import product_by_key

product = product_by_key(sys.argv[1])
value = product
for part in sys.argv[2].split("."):
    value = value[part]
print(value)
PY
}

REGION="$(read_product_field _aws.region)"
INSTANCE_TYPE="$(read_product_field recommended_instance_type)"
PROFILE="$(read_product_field profile)"

if [[ "$PROFILE" != "eks-admin-bastion" ]]; then
  echo "This smoke test only supports the eks-admin-bastion profile: $PRODUCT_KEY" >&2
  exit 2
fi

if [[ -n "${CORENOVA_SMOKE_EKS_CLUSTER_NAME:-}" ]]; then
  if [[ ! "$CORENOVA_SMOKE_EKS_CLUSTER_NAME" =~ ^[0-9A-Za-z][A-Za-z0-9_-]*$ ]]; then
    echo "Invalid CORENOVA_SMOKE_EKS_CLUSTER_NAME" >&2
    exit 2
  fi
fi

STAMP="$(date -u +%Y%m%d%H%M%S)"
NAME="builder-ami-ssm-smoke-${PRODUCT_KEY}-${STAMP}"
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
}
trap cleanup EXIT

VPC_ID="$(aws ec2 describe-subnets \
  --region "$REGION" \
  --subnet-ids "$CORENOVA_SMOKE_SUBNET_ID" \
  --query 'Subnets[0].VpcId' \
  --output text)"

SG_ID="$(aws ec2 create-security-group \
  --region "$REGION" \
  --group-name "$NAME" \
  --description "No-ingress SSM smoke test for $PRODUCT_KEY" \
  --vpc-id "$VPC_ID" \
  --tag-specifications "ResourceType=security-group,Tags=[{Key=Name,Value=${NAME}},{Key=Project,Value=builder-ami},{Key=Purpose,Value=ssm-smoke-test}]" \
  --query GroupId \
  --output text)"

NETWORK_INTERFACES="$(jq -cn \
  --arg subnet "$CORENOVA_SMOKE_SUBNET_ID" \
  --arg sg "$SG_ID" \
  --argjson public_ip "$ALLOW_PUBLIC_IP" \
  '[{DeviceIndex:0,SubnetId:$subnet,Groups:[$sg],AssociatePublicIpAddress:$public_ip}]')"

INSTANCE_ID="$(aws ec2 run-instances \
  --region "$REGION" \
  --image-id "$AMI_ID" \
  --instance-type "$INSTANCE_TYPE" \
  --iam-instance-profile "Name=$CORENOVA_SMOKE_INSTANCE_PROFILE_NAME" \
  --network-interfaces "$NETWORK_INTERFACES" \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=1 \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${NAME}},{Key=Project,Value=builder-ami},{Key=ProductKey,Value=${PRODUCT_KEY}},{Key=Purpose,Value=ssm-smoke-test}]" \
    "ResourceType=network-interface,Tags=[{Key=Name,Value=${NAME}},{Key=Project,Value=builder-ami},{Key=ProductKey,Value=${PRODUCT_KEY}},{Key=Purpose,Value=ssm-smoke-test}]" \
    "ResourceType=volume,Tags=[{Key=Name,Value=${NAME}},{Key=Project,Value=builder-ami},{Key=ProductKey,Value=${PRODUCT_KEY}},{Key=Purpose,Value=ssm-smoke-test}]" \
  --query 'Instances[0].InstanceId' \
  --output text)"

aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"

PUBLIC_IP="$(aws ec2 describe-instances \
  --region "$REGION" \
  --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text)"
if [[ "$ALLOW_PUBLIC_IP" == "false" && "$PUBLIC_IP" != "None" && "$PUBLIC_IP" != "null" && -n "$PUBLIC_IP" ]]; then
  echo "Smoke instance unexpectedly has a public IP: $PUBLIC_IP" >&2
  exit 1
fi
if [[ "$ALLOW_PUBLIC_IP" == "true" && ( "$PUBLIC_IP" == "None" || "$PUBLIC_IP" == "null" || -z "$PUBLIC_IP" ) ]]; then
  echo "Smoke instance needs an ephemeral public IP for outbound SSM access in this cost-capped mode" >&2
  exit 1
fi

INGRESS_COUNT="$(aws ec2 describe-security-groups \
  --region "$REGION" \
  --group-ids "$SG_ID" \
  --query 'length(SecurityGroups[0].IpPermissions)' \
  --output text)"
if [[ "$INGRESS_COUNT" != "0" ]]; then
  echo "Smoke security group unexpectedly has ingress rules" >&2
  exit 1
fi

SSM_STATUS=""
for _ in $(seq 1 60); do
  SSM_STATUS="$(aws ssm describe-instance-information \
    --region "$REGION" \
    --filters "Key=InstanceIds,Values=$INSTANCE_ID" \
    --query 'InstanceInformationList[0].PingStatus' \
    --output text 2>/dev/null || true)"
  if [[ "$SSM_STATUS" == "Online" ]]; then
    break
  fi
  sleep 10
done
if [[ "$SSM_STATUS" != "Online" ]]; then
  echo "Instance did not register as an online Systems Manager managed node" >&2
  exit 1
fi

REMOTE_COMMANDS=(
  'set -euo pipefail'
  'corenova-eks-check'
  'corenova-eks-doctor --help >/dev/null'
  'id corenova-operator'
  'test "$(id -u corenova-operator)" -ne 0'
  'systemctl is-enabled --quiet amazon-ssm-agent'
  'systemctl is-active --quiet amazon-ssm-agent'
  'agent_version="$(amazon-ssm-agent -version 2>&1 | sed -nE "s/.*([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+).*/\1/p" | head -1)"; test -n "$agent_version"; test "$(printf "%s\n%s\n" "3.1.1374.0" "$agent_version" | sort -V | head -1)" = "3.1.1374.0"'
  'test -z "$(find /root /home -xdev -type f \( -path "*/.aws/credentials" -o -path "*/.kube/config" -o -name .bash_history -o -name .zsh_history \) -size +0c -print -quit 2>/dev/null)"'
  '! find /root /home /etc/corenova /opt/corenova -xdev -type f -size -2M -print0 2>/dev/null | xargs -0 -r grep -IlE "BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY" | grep -q .'
  'token="$(curl -fsS -X PUT -H "X-aws-ec2-metadata-token-ttl-seconds: 60" http://169.254.169.254/latest/api/token)"; test -n "$token"; curl -fsS -H "X-aws-ec2-metadata-token: $token" http://169.254.169.254/latest/meta-data/instance-id >/dev/null'
)

if [[ -n "${CORENOVA_SMOKE_EKS_CLUSTER_NAME:-}" ]]; then
  EKS_REGION="${CORENOVA_SMOKE_EKS_REGION:-$REGION}"
  printf -v EKS_CHECK \
    'corenova-eks-doctor --cluster %q --region %q --namespace %q --output json' \
    "$CORENOVA_SMOKE_EKS_CLUSTER_NAME" "$EKS_REGION" "${CORENOVA_SMOKE_EKS_NAMESPACE:-default}"
  REMOTE_COMMANDS+=("$EKS_CHECK")
fi

PARAMETERS="$(printf '%s\n' "${REMOTE_COMMANDS[@]}" | jq -R . | jq -sc '{commands:.}')"
COMMAND_ID="$(aws ssm send-command \
  --region "$REGION" \
  --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --comment "CoreNova EKS Admin Bastion no-ingress smoke test" \
  --parameters "$PARAMETERS" \
  --query 'Command.CommandId' \
  --output text)"

set +e
aws ssm wait command-executed \
  --region "$REGION" \
  --command-id "$COMMAND_ID" \
  --instance-id "$INSTANCE_ID"
WAITER_RC=$?
set -e

INVOCATION="$(aws ssm get-command-invocation \
  --region "$REGION" \
  --command-id "$COMMAND_ID" \
  --instance-id "$INSTANCE_ID" \
  --output json)"
printf '%s\n' "$INVOCATION" | jq -r '.StandardOutputContent, .StandardErrorContent'

STATUS="$(printf '%s\n' "$INVOCATION" | jq -r '.Status')"
if [[ "$WAITER_RC" -ne 0 || "$STATUS" != "Success" ]]; then
  echo "SSM smoke command failed with status: $STATUS" >&2
  exit 1
fi

echo "SSM_SMOKE_OK $PRODUCT_KEY $AMI_ID $INSTANCE_ID"
