#!/usr/bin/env bash

set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
trust_policy="${repository_root}/marketplace/eks-admin-bastion/iam/marketplace-instance-publisher-trust-policy.json"
permissions_policy="${repository_root}/marketplace/eks-admin-bastion/iam/marketplace-instance-publisher-policy.json"
role_name="CoreNovaMarketplaceInstancePublisherRole"
policy_name="CoreNovaMarketplaceInstancePublisherPolicy"
expected_account="582920575154"
policy_arn="arn:aws:iam::${expected_account}:policy/${policy_name}"

identity="$(aws sts get-caller-identity --output json)"
account="$(jq -r '.Account // empty' <<<"$identity")"
arn="$(jq -r '.Arn // empty' <<<"$identity")"

if [[ "$account" != "$expected_account" ]]; then
  echo "AWS caller account mismatch: expected $expected_account, got ${account:-unknown}" >&2
  exit 1
fi
if [[ "$arn" != "arn:aws:iam::${expected_account}:root" ]]; then
  echo "This one-time bootstrap requires the seller account root caller; got ${arn:-unknown}" >&2
  exit 1
fi

if aws iam get-policy --policy-arn "$policy_arn" >/dev/null 2>&1; then
  echo "Publisher policy already exists: $policy_arn"
else
  aws iam create-policy \
    --policy-name "$policy_name" \
    --description "Publishes the reviewed EKS Admin instance-type and hourly-dimension expansion only." \
    --policy-document "file://${permissions_policy}" \
    --tags \
      Key=ManagedBy,Value=bootstrap-script \
      Key=Project,Value=builder-ami \
      Key=Product,Value=eks-admin-bastion \
      Key=Purpose,Value=instance-type-expansion \
    --query 'Policy.Arn' \
    --output text
fi

if aws iam get-role --role-name "$role_name" >/dev/null 2>&1; then
  echo "Updating existing publisher role trust policy: $role_name"
  aws iam update-assume-role-policy \
    --role-name "$role_name" \
    --policy-document "file://${trust_policy}"
  aws iam put-role-permissions-boundary \
    --role-name "$role_name" \
    --permissions-boundary "$policy_arn"
else
  aws iam create-role \
    --role-name "$role_name" \
    --description "MFA-governed publisher for reviewed EKS Admin instance-type expansion plans." \
    --max-session-duration 3600 \
    --permissions-boundary "$policy_arn" \
    --assume-role-policy-document "file://${trust_policy}" \
    --tags \
      Key=ManagedBy,Value=bootstrap-script \
      Key=Project,Value=builder-ami \
      Key=Product,Value=eks-admin-bastion \
      Key=Purpose,Value=instance-type-expansion \
    --query 'Role.Arn' \
    --output text
fi

aws iam attach-role-policy \
  --role-name "$role_name" \
  --policy-arn "$policy_arn"

echo "Publisher role ready: arn:aws:iam::${expected_account}:role/${role_name}"
