#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
ACCOUNT_ID=582920575154
IAM_DIR="$ROOT_DIR/marketplace/eks-admin-bastion/iam"

caller="$(aws sts get-caller-identity --query Arn --output text)"
if [[ "$caller" != "arn:aws:iam::${ACCOUNT_ID}:root" ]]; then
  echo "AMI execution-policy bootstrap requires the seller root caller; got $caller" >&2
  exit 2
fi

sync_existing_policy() {
  local policy_name="$1" policy_file="$2"
  local policy_arn="arn:aws:iam::${ACCOUNT_ID}:policy/${policy_name}"
  aws iam get-policy --policy-arn "$policy_arn" >/dev/null

  local current_version current_document desired_document oldest
  current_version="$(aws iam get-policy --policy-arn "$policy_arn" \
    --query 'Policy.DefaultVersionId' --output text)"
  current_document="$(aws iam get-policy-version \
    --policy-arn "$policy_arn" --version-id "$current_version" \
    --query 'PolicyVersion.Document' --output json | jq -cS .)"
  desired_document="$(jq -cS . "$policy_file")"
  if [[ "$current_document" == "$desired_document" ]]; then
    echo "UNCHANGED $policy_name"
    return
  fi

  if [[ "$(aws iam list-policy-versions --policy-arn "$policy_arn" \
    --query 'length(Versions)' --output text)" == 5 ]]; then
    oldest="$(aws iam list-policy-versions --policy-arn "$policy_arn" \
      --query 'sort_by(Versions[?IsDefaultVersion==`false`],&CreateDate)[0].VersionId' \
      --output text)"
    aws iam delete-policy-version --policy-arn "$policy_arn" --version-id "$oldest"
  fi
  aws iam create-policy-version \
    --policy-arn "$policy_arn" --policy-document "file://$policy_file" \
    --set-as-default >/dev/null
  echo "UPDATED $policy_name"
}

sync_existing_policy CoreNovaAmiBuilderPolicy "$IAM_DIR/ami-builder-policy.json"
sync_existing_policy CoreNovaEksBastionSmokeRunnerPolicy "$IAM_DIR/ssm-smoke-runner-policy.json"
