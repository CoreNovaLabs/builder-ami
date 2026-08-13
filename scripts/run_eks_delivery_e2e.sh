#!/usr/bin/env bash
set -euo pipefail

PRODUCT_KEY="${1:?usage: scripts/run_eks_delivery_e2e.sh <product-key> <ami-id>}"
AMI_ID="${2:?usage: scripts/run_eks_delivery_e2e.sh <product-key> <ami-id>}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source scripts/lib/aws_identity.sh

assert_corenova_assumed_role CoreNovaEksDeliveryE2ERole
: "${GITHUB_RUN_ID:?GITHUB_RUN_ID is required for disposable resource names}"

REGION="${AWS_REGION:-us-east-1}"
RUN_TOKEN="${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT:-1}"
ENV_STACK="corenova-eks-e2e-${RUN_TOKEN}"
IDENTITY_STACK="corenova-identity-e2e-${RUN_TOKEN}"
AUDITED_STACK="corenova-audited-e2e-${RUN_TOKEN}"
NEGATIVE_STACK="corenova-privileged-negative-${RUN_TOKEN}"
REPORT_DIR="operations/reports/e2e"
CFN_ROLE_ARN="arn:aws:iam::582920575154:role/CoreNovaEksDeliveryE2ECloudFormationRole"
mkdir -p "$REPORT_DIR"

case "$PRODUCT_KEY" in
  eks-admin-bastion-al2023-x86_64)
    ARCHITECTURE=x86_64
    IDENTITY_INSTANCE_TYPE=t3.micro
    AUDITED_INSTANCE_TYPE=t3.small
    ;;
  eks-admin-bastion-al2023-arm64)
    ARCHITECTURE=arm64
    IDENTITY_INSTANCE_TYPE=t4g.micro
    AUDITED_INSTANCE_TYPE=t4g.small
    ;;
  *)
    echo "Unsupported EKS candidate: $PRODUCT_KEY" >&2
    exit 2
    ;;
esac

CALLER_ARN="$(aws sts get-caller-identity --query Arn --output text)"
RUNNER_ROLE_ARN="arn:aws:iam::582920575154:role/CoreNovaEksDeliveryE2ERole"
if [[ "$CALLER_ARN" != arn:aws:sts::582920575154:assumed-role/CoreNovaEksDeliveryE2ERole/* ]]; then
  echo "Unexpected E2E caller: $CALLER_ARN" >&2
  exit 2
fi

stack_exists() {
  aws cloudformation describe-stacks --region "$REGION" --stack-name "$1" >/dev/null 2>&1
}

terminate_active_sessions() {
  local instance_id="$1" session_id
  [[ -n "$instance_id" ]] || return 0
  while IFS= read -r session_id; do
    [[ -n "$session_id" && "$session_id" != None ]] || continue
    aws ssm terminate-session --region "$REGION" --session-id "$session_id" >/dev/null
  done < <(
    aws ssm describe-sessions --region "$REGION" --state Active \
      --filters "key=Target,value=$instance_id" \
      --query 'Sessions[].SessionId' --output text 2>/dev/null | tr '\t' '\n'
  )
}

delete_stack() {
  local name="$1"
  if stack_exists "$name"; then
    aws cloudformation delete-stack --region "$REGION" --stack-name "$name"
    aws cloudformation wait stack-delete-complete --region "$REGION" --stack-name "$name"
  fi
}

cleanup() {
  local rc=$?
  local cleanup_rc=0 final_rc
  set +e
  terminate_active_sessions "${AUDITED_INSTANCE_ID:-}" || cleanup_rc=1
  terminate_active_sessions "${IDENTITY_INSTANCE_ID:-}" || cleanup_rc=1
  delete_stack "$NEGATIVE_STACK" || cleanup_rc=1
  delete_stack "$AUDITED_STACK" || cleanup_rc=1
  delete_stack "$IDENTITY_STACK" || cleanup_rc=1
  if [[ -n "${AUDIT_LOG_GROUP:-}" ]]; then
    if aws logs describe-log-groups --region "$REGION" --log-group-name-prefix "$AUDIT_LOG_GROUP" \
      --query 'length(logGroups)' --output text 2>/dev/null | grep -Eq '^[1-9]'; then
      aws logs delete-log-group --region "$REGION" --log-group-name "$AUDIT_LOG_GROUP" >/dev/null 2>&1 || cleanup_rc=1
    fi
  fi
  delete_stack "$ENV_STACK" || cleanup_rc=1
  if [[ -n "${CLUSTER_NAME:-}" ]]; then
    control_plane_log_group="/aws/eks/${CLUSTER_NAME}/cluster"
    if aws logs describe-log-groups --region "$REGION" --log-group-name-prefix "$control_plane_log_group" \
      --query 'length(logGroups)' --output text 2>/dev/null | grep -Eq '^[1-9]'; then
      aws logs delete-log-group --region "$REGION" --log-group-name "$control_plane_log_group" >/dev/null 2>&1 || cleanup_rc=1
    fi
  fi
  final_rc="$rc"
  if [[ "$final_rc" == 0 && "$cleanup_rc" != 0 ]]; then
    final_rc=1
  fi
  jq -n --arg product "$PRODUCT_KEY" --arg ami_id "$AMI_ID" --arg run_id "$RUN_TOKEN" \
    --argjson test_exit_code "$rc" --argjson cleanup_exit_code "$cleanup_rc" --argjson final_exit_code "$final_rc" \
    '{product:$product,ami_id:$ami_id,run_id:$run_id,test_exit_code:$test_exit_code,cleanup_exit_code:$cleanup_exit_code,final_exit_code:$final_exit_code}' \
    > "$REPORT_DIR/cleanup-result.json"
  trap - EXIT
  exit "$final_rc"
}
trap cleanup EXIT

output() {
  aws cloudformation describe-stacks \
    --region "$REGION" \
    --stack-name "$1" \
    --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue | [0]" \
    --output text
}

wait_for_ssm() {
  local instance_id="$1" status=""
  for _ in $(seq 1 90); do
    status="$(aws ssm describe-instance-information \
      --region "$REGION" \
      --filters "Key=InstanceIds,Values=$instance_id" \
      --query 'InstanceInformationList[0].PingStatus' \
      --output text 2>/dev/null || true)"
    [[ "$status" == Online ]] && return 0
    sleep 10
  done
  echo "SSM managed node did not become Online: $instance_id" >&2
  return 1
}

assert_instance_safety() {
  local instance_id="$1" sg_id="$2"
  aws ec2 describe-instances --region "$REGION" --instance-ids "$instance_id" \
    --query 'Reservations[0].Instances[0].{PublicIp:PublicIpAddress,HttpTokens:MetadataOptions.HttpTokens,HopLimit:MetadataOptions.HttpPutResponseHopLimit}' \
    --output json | tee -a "$REPORT_DIR/instance-safety.jsonl"
  [[ "$(aws ec2 describe-instances --region "$REGION" --instance-ids "$instance_id" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)" == None ]]
  [[ "$(aws ec2 describe-instances --region "$REGION" --instance-ids "$instance_id" --query 'Reservations[0].Instances[0].MetadataOptions.HttpTokens' --output text)" == required ]]
  [[ "$(aws ec2 describe-security-groups --region "$REGION" --group-ids "$sg_id" --query 'length(SecurityGroups[0].IpPermissions)' --output text)" == 0 ]]
  local volume_id
  volume_id="$(aws ec2 describe-instances --region "$REGION" --instance-ids "$instance_id" --query 'Reservations[0].Instances[0].BlockDeviceMappings[0].Ebs.VolumeId' --output text)"
  [[ "$(aws ec2 describe-volumes --region "$REGION" --volume-ids "$volume_id" --query 'Volumes[0].Encrypted' --output text)" == True ]]
}

run_command() {
  local instance_id="$1" command="$2" name="$3" command_id status
  command_id="$(aws ssm send-command \
    --region "$REGION" \
    --instance-ids "$instance_id" \
    --document-name AWS-RunShellScript \
    --parameters "$(jq -cn --arg c "$command" '{commands:[$c]}')" \
    --query 'Command.CommandId' --output text)"
  aws ssm wait command-executed --region "$REGION" --command-id "$command_id" --instance-id "$instance_id"
  aws ssm get-command-invocation --region "$REGION" --command-id "$command_id" --instance-id "$instance_id" \
    --output json > "$REPORT_DIR/${name}.json"
  status="$(jq -r .Status "$REPORT_DIR/${name}.json")"
  jq -r '.StandardOutputContent,.StandardErrorContent' "$REPORT_DIR/${name}.json"
  [[ "$status" == Success ]]
}

wait_for_no_active_sessions() {
  local instance_id="$1" count=""
  for _ in $(seq 1 30); do
    count="$(aws ssm describe-sessions --region "$REGION" --state Active \
      --filters "key=Target,value=$instance_id" --query 'length(Sessions)' --output text)"
    [[ "$count" == 0 ]] && return 0
    sleep 2
  done
  echo "Active SSM sessions remain for $instance_id" >&2
  return 1
}

python3 scripts/package_eks_admin_delivery_assets.py --output-dir "$REPORT_DIR/assets" >/dev/null
TEMPLATE_DIR="$REPORT_DIR/assets/$ARCHITECTURE"

aws cloudformation deploy \
  --region "$REGION" \
  --stack-name "$ENV_STACK" \
  --template-file marketplace/eks-admin-bastion/tests/e2e-environment.yaml \
  --role-arn "$CFN_ROLE_ARN" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides RunnerRoleArn="$RUNNER_ROLE_ARN" RunId="$RUN_TOKEN" \
  --tags Project=builder-ami Purpose=eks-delivery-e2e RunId="$RUN_TOKEN"

VPC_ID="$(output "$ENV_STACK" VpcId)"
PRIVATE_SUBNET_ID="$(output "$ENV_STACK" PrivateSubnetId)"
CLUSTER_NAME="$(output "$ENV_STACK" ClusterName)"
CLUSTER_SG_ID="$(output "$ENV_STACK" ClusterSecurityGroupId)"
OPERATOR_ONE_ARN="$(output "$ENV_STACK" OperatorOneRoleArn)"
OPERATOR_TWO_ARN="$(output "$ENV_STACK" OperatorTwoRoleArn)"

aws cloudformation deploy \
  --region "$REGION" \
  --stack-name "$IDENTITY_STACK" \
  --template-file "$TEMPLATE_DIR/identity-relay.yaml" \
  --role-arn "$CFN_ROLE_ARN" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    AmiId="$AMI_ID" VpcId="$VPC_ID" SubnetId="$PRIVATE_SUBNET_ID" \
    ClusterName="$CLUSTER_NAME" ClusterSecurityGroupId="$CLUSTER_SG_ID" \
    CreateClusterSecurityGroupIngress=Yes CreateOperatorAccessEntry=Yes \
    OperatorRoleArn="$OPERATOR_ONE_ARN" EksAccessPolicyName=AmazonEKSViewPolicy \
    AccessScope=Namespace KubernetesNamespace=default \
    InstanceArchitecture="$ARCHITECTURE" InstanceType="$IDENTITY_INSTANCE_TYPE" \
  --tags Project=builder-ami Purpose=eks-delivery-e2e RunId="$RUN_TOKEN"

IDENTITY_INSTANCE_ID="$(output "$IDENTITY_STACK" InstanceId)"
IDENTITY_SG_ID="$(output "$IDENTITY_STACK" RelaySecurityGroupId)"
wait_for_ssm "$IDENTITY_INSTANCE_ID"
assert_instance_safety "$IDENTITY_INSTANCE_ID" "$IDENTITY_SG_ID"
run_command "$IDENTITY_INSTANCE_ID" \
  "set -e; if aws eks describe-cluster --region '$REGION' --name '$CLUSTER_NAME' >/tmp/eks.out 2>/tmp/eks.err; then exit 9; fi; grep -E 'AccessDenied|not authorized' /tmp/eks.err" \
  identity-instance-role-denied

python3 marketplace/eks-admin-bastion/client/corenova_eks_connect.py \
  --stack-name "$IDENTITY_STACK" --region "$REGION" --role-arn "$OPERATOR_ONE_ARN" \
  --namespace default -- auth can-i get pods --namespace default | tee "$REPORT_DIR/operator-one-default.txt"
grep -qx yes "$REPORT_DIR/operator-one-default.txt"
python3 marketplace/eks-admin-bastion/client/corenova_eks_connect.py \
  --stack-name "$IDENTITY_STACK" --region "$REGION" --role-arn "$OPERATOR_ONE_ARN" \
  -- auth whoami -o json > "$REPORT_DIR/operator-one-whoami.json"
jq -e '.status.userInfo.username | contains("OperatorOneRole")' "$REPORT_DIR/operator-one-whoami.json"
python3 marketplace/eks-admin-bastion/client/corenova_eks_connect.py \
  --stack-name "$IDENTITY_STACK" --region "$REGION" --role-arn "$OPERATOR_TWO_ARN" \
  --namespace default -- auth can-i get pods --namespace default | tee "$REPORT_DIR/operator-two-default.txt"
grep -qx yes "$REPORT_DIR/operator-two-default.txt"
python3 marketplace/eks-admin-bastion/client/corenova_eks_connect.py \
  --stack-name "$IDENTITY_STACK" --region "$REGION" --role-arn "$OPERATOR_TWO_ARN" \
  -- auth whoami -o json > "$REPORT_DIR/operator-two-whoami.json"
jq -e '.status.userInfo.username | contains("OperatorTwoRole")' "$REPORT_DIR/operator-two-whoami.json"
[[ "$(jq -r .status.userInfo.username "$REPORT_DIR/operator-one-whoami.json")" != "$(jq -r .status.userInfo.username "$REPORT_DIR/operator-two-whoami.json")" ]]

set +e
python3 marketplace/eks-admin-bastion/client/corenova_eks_connect.py \
  --stack-name "$IDENTITY_STACK" --region "$REGION" --role-arn "$OPERATOR_ONE_ARN" \
  --local-port 18445 -- definitely-not-a-kubectl-command \
  >"$REPORT_DIR/kubectl-failure.out" 2>"$REPORT_DIR/kubectl-failure.err"
KUBECTL_FAILURE_RC=$?
set -e
[[ "$KUBECTL_FAILURE_RC" -ne 0 ]]
python3 - <<'PY'
import socket
with socket.socket() as probe:
    probe.bind(("127.0.0.1", 18445))
PY
wait_for_no_active_sessions "$IDENTITY_INSTANCE_ID"

python3 -m http.server 18444 --bind 127.0.0.1 >"$REPORT_DIR/busy-port-server.log" 2>&1 &
BUSY_PID=$!
set +e
python3 marketplace/eks-admin-bastion/client/corenova_eks_connect.py \
  --stack-name "$IDENTITY_STACK" --region "$REGION" --role-arn "$OPERATOR_ONE_ARN" \
  --local-port 18444 -- auth can-i get pods --namespace default \
  >"$REPORT_DIR/busy-port.out" 2>"$REPORT_DIR/busy-port.err"
BUSY_RC=$?
set -e
kill "$BUSY_PID" 2>/dev/null || true
wait "$BUSY_PID" 2>/dev/null || true
[[ "$BUSY_RC" == 2 ]]
grep -q 'already in use' "$REPORT_DIR/busy-port.err"

aws cloudformation deploy \
  --region "$REGION" --stack-name "$IDENTITY_STACK" \
  --template-file "$TEMPLATE_DIR/identity-relay.yaml" --capabilities CAPABILITY_IAM \
  --role-arn "$CFN_ROLE_ARN" \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    AmiId="$AMI_ID" VpcId="$VPC_ID" SubnetId="$PRIVATE_SUBNET_ID" \
    ClusterName="$CLUSTER_NAME" ClusterSecurityGroupId="$CLUSTER_SG_ID" \
    CreateClusterSecurityGroupIngress=Yes CreateOperatorAccessEntry=Yes \
    OperatorRoleArn="$OPERATOR_ONE_ARN" EksAccessPolicyName=AmazonEKSViewPolicy \
    AccessScope=Namespace KubernetesNamespace=default \
    InstanceArchitecture="$ARCHITECTURE" InstanceType="$IDENTITY_INSTANCE_TYPE"
delete_stack "$IDENTITY_STACK"

set +e
NEGATIVE_CREATE="$(aws cloudformation create-stack \
  --region "$REGION" --stack-name "$NEGATIVE_STACK" \
  --template-body "file://$TEMPLATE_DIR/audited-workstation.yaml" \
  --role-arn "$CFN_ROLE_ARN" \
  --capabilities CAPABILITY_IAM \
  --parameters \
    ParameterKey=AmiId,ParameterValue="$AMI_ID" \
    ParameterKey=VpcId,ParameterValue="$VPC_ID" \
    ParameterKey=SubnetId,ParameterValue="$PRIVATE_SUBNET_ID" \
    ParameterKey=ClusterName,ParameterValue="$CLUSTER_NAME" \
    ParameterKey=ClusterSecurityGroupId,ParameterValue="$CLUSTER_SG_ID" \
    ParameterKey=EksAccessPolicyName,ParameterValue=AmazonEKSAdminPolicy \
    ParameterKey=InstanceArchitecture,ParameterValue="$ARCHITECTURE" \
    ParameterKey=InstanceType,ParameterValue="$AUDITED_INSTANCE_TYPE" \
  2>"$REPORT_DIR/privileged-negative.err")"
NEGATIVE_RC=$?
set -e
printf '%s\n' "$NEGATIVE_CREATE" > "$REPORT_DIR/privileged-negative.out"
if [[ "$NEGATIVE_RC" == 0 ]]; then
  set +e
  aws cloudformation wait stack-create-complete --region "$REGION" --stack-name "$NEGATIVE_STACK"
  NEGATIVE_WAITER_RC=$?
  set -e
  [[ "$NEGATIVE_WAITER_RC" -ne 0 ]]
  NEGATIVE_STATUS="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$NEGATIVE_STACK" --query 'Stacks[0].StackStatus' --output text)"
  [[ "$NEGATIVE_STATUS" == ROLLBACK_COMPLETE || "$NEGATIVE_STATUS" == CREATE_FAILED ]]
else
  grep -Eqi 'rule|acknowledgement|parameter|validation' "$REPORT_DIR/privileged-negative.err"
fi
delete_stack "$NEGATIVE_STACK"

aws cloudformation deploy \
  --region "$REGION" \
  --stack-name "$AUDITED_STACK" \
  --template-file "$TEMPLATE_DIR/audited-workstation.yaml" \
  --role-arn "$CFN_ROLE_ARN" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    AmiId="$AMI_ID" VpcId="$VPC_ID" SubnetId="$PRIVATE_SUBNET_ID" \
    ClusterName="$CLUSTER_NAME" ClusterSecurityGroupId="$CLUSTER_SG_ID" \
    CreateClusterSecurityGroupIngress=Yes EksAccessPolicyName=AmazonEKSViewPolicy \
    AccessScope=Namespace KubernetesNamespace=default \
    InstanceArchitecture="$ARCHITECTURE" InstanceType="$AUDITED_INSTANCE_TYPE" \
    IdleSessionTimeoutMinutes=20 MaxSessionDurationMinutes=60 \
  --tags Project=builder-ami Purpose=eks-delivery-e2e RunId="$RUN_TOKEN"

AUDITED_INSTANCE_ID="$(output "$AUDITED_STACK" InstanceId)"
AUDITED_SG_ID="$(output "$AUDITED_STACK" WorkstationSecurityGroupId)"
AUDIT_DOCUMENT="$(output "$AUDITED_STACK" SessionDocumentName)"
AUDIT_LOG_GROUP="$(output "$AUDITED_STACK" AuditLogGroupName)"
wait_for_ssm "$AUDITED_INSTANCE_ID"
assert_instance_safety "$AUDITED_INSTANCE_ID" "$AUDITED_SG_ID"

MARKER="CORENOVA_AUDIT_${RUN_TOKEN//-/_}"
REMOTE_AUDIT_COMMAND="set -e; test \"\$(id -u)\" -ne 0; test \"\$(id -un)\" = corenova-operator; aws eks update-kubeconfig --region '$REGION' --name '$CLUSTER_NAME' >/dev/null; test \"\$(kubectl auth can-i get pods --namespace default)\" = yes; test \"\$(kubectl auth can-i get pods --namespace kube-system)\" = no; echo '$MARKER'"
REMOTE_AUDIT_COMMAND_B64="$(printf '%s' "$REMOTE_AUDIT_COMMAND" | base64 | tr -d '\n')"
export AUDITED_INSTANCE_ID AUDIT_DOCUMENT REGION CLUSTER_NAME MARKER REMOTE_AUDIT_COMMAND_B64
expect <<'EXPECT' | tee "$REPORT_DIR/audited-session.txt"
set timeout 120
spawn aws ssm start-session --region $env(REGION) --target $env(AUDITED_INSTANCE_ID) --document-name $env(AUDIT_DOCUMENT)
sleep 8
send -- "echo '$env(REMOTE_AUDIT_COMMAND_B64)' | base64 -d | bash\r"
expect {
  -re "^$env(MARKER)\\r?$" {}
  timeout {exit 7}
  eof {exit 8}
}
send -- "exit\r"
expect eof
EXPECT
wait_for_no_active_sessions "$AUDITED_INSTANCE_ID"

LOG_FOUND=false
for _ in $(seq 1 60); do
  if aws logs filter-log-events --region "$REGION" --log-group-name "$AUDIT_LOG_GROUP" \
    --filter-pattern "$MARKER" --query 'events[0].message' --output text 2>/dev/null | grep -q "$MARKER"; then
    LOG_FOUND=true
    break
  fi
  sleep 5
done
[[ "$LOG_FOUND" == true ]]

aws cloudformation deploy \
  --region "$REGION" --stack-name "$AUDITED_STACK" \
  --template-file "$TEMPLATE_DIR/audited-workstation.yaml" --capabilities CAPABILITY_IAM \
  --role-arn "$CFN_ROLE_ARN" \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    AmiId="$AMI_ID" VpcId="$VPC_ID" SubnetId="$PRIVATE_SUBNET_ID" \
    ClusterName="$CLUSTER_NAME" ClusterSecurityGroupId="$CLUSTER_SG_ID" \
    CreateClusterSecurityGroupIngress=Yes EksAccessPolicyName=AmazonEKSViewPolicy \
    AccessScope=Namespace KubernetesNamespace=default \
    InstanceArchitecture="$ARCHITECTURE" InstanceType="$AUDITED_INSTANCE_TYPE" \
    IdleSessionTimeoutMinutes=20 MaxSessionDurationMinutes=60
delete_stack "$AUDITED_STACK"
aws logs describe-log-groups --region "$REGION" --log-group-name-prefix "$AUDIT_LOG_GROUP" \
  --query 'logGroups[?logGroupName==`'"$AUDIT_LOG_GROUP"'`].logGroupName | [0]' --output text | grep -Fx "$AUDIT_LOG_GROUP"
aws logs delete-log-group --region "$REGION" --log-group-name "$AUDIT_LOG_GROUP"
AUDIT_LOG_GROUP=""

jq -n \
  --arg product "$PRODUCT_KEY" --arg ami_id "$AMI_ID" --arg architecture "$ARCHITECTURE" \
  --arg environment_stack "$ENV_STACK" --arg cluster "$CLUSTER_NAME" \
  --arg operator_one "$OPERATOR_ONE_ARN" --arg operator_two "$OPERATOR_TWO_ARN" \
  '{status:"SUCCEEDED",product:$product,ami_id:$ami_id,architecture:$architecture,environment_stack:$environment_stack,cluster:$cluster,operator_roles:[$operator_one,$operator_two]}' \
  > "$REPORT_DIR/result.json"
echo "EKS_DELIVERY_E2E_OK $PRODUCT_KEY $AMI_ID"
