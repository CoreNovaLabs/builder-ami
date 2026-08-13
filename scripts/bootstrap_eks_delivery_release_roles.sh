#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
ACCOUNT_ID=582920575154
IAM_DIR="$ROOT_DIR/marketplace/eks-admin-bastion/iam"
TRUST_FILE="$IAM_DIR/github-main-trust-policy.json"
BUCKET=corenova-marketplace-assets-582920575154

identity="$(aws sts get-caller-identity --output json)"
caller="$(jq -r .Arn <<<"$identity")"
if [[ "$caller" != "arn:aws:iam::${ACCOUNT_ID}:root" ]]; then
  echo "One-time IAM/S3 bootstrap requires the seller root caller; got $caller" >&2
  exit 2
fi

sync_policy() {
  local policy_name="$1" policy_file="$2" description="$3"
  local policy_arn="arn:aws:iam::${ACCOUNT_ID}:policy/${policy_name}"
  if ! aws iam get-policy --policy-arn "$policy_arn" >/dev/null 2>&1; then
    aws iam create-policy \
      --policy-name "$policy_name" --description "$description" \
      --policy-document "file://$policy_file" \
      --tags Key=Project,Value=builder-ami Key=Product,Value=eks-admin-bastion \
      >/dev/null
    return
  fi
  local current_document desired_document
  current_document="$(aws iam get-policy-version \
    --policy-arn "$policy_arn" \
    --version-id "$(aws iam get-policy --policy-arn "$policy_arn" --query 'Policy.DefaultVersionId' --output text)" \
    --query 'PolicyVersion.Document' --output json | jq -cS .)"
  desired_document="$(jq -cS . "$policy_file")"
  if [[ "$current_document" == "$desired_document" ]]; then
    return
  fi
  if [[ "$(aws iam list-policy-versions --policy-arn "$policy_arn" --query 'length(Versions)' --output text)" == 5 ]]; then
    oldest="$(aws iam list-policy-versions --policy-arn "$policy_arn" \
      --query 'sort_by(Versions[?IsDefaultVersion==`false`],&CreateDate)[0].VersionId' --output text)"
    aws iam delete-policy-version --policy-arn "$policy_arn" --version-id "$oldest"
  fi
  aws iam create-policy-version \
    --policy-arn "$policy_arn" --policy-document "file://$policy_file" \
    --set-as-default >/dev/null
}

ensure_policy_role() {
  local role_name="$1" policy_name="$2" policy_file="$3" description="$4" trust_file="${5:-$TRUST_FILE}"
  local policy_arn="arn:aws:iam::${ACCOUNT_ID}:policy/${policy_name}"
  sync_policy "$policy_name" "$policy_file" "$description"
  if aws iam get-role --role-name "$role_name" >/dev/null 2>&1; then
    aws iam update-assume-role-policy --role-name "$role_name" --policy-document "file://$trust_file"
    aws iam put-role-permissions-boundary --role-name "$role_name" --permissions-boundary "$policy_arn"
  else
    aws iam create-role \
      --role-name "$role_name" --description "$description" \
      --max-session-duration 3600 --permissions-boundary "$policy_arn" \
      --assume-role-policy-document "file://$trust_file" \
      --tags Key=Project,Value=builder-ami Key=Product,Value=eks-admin-bastion \
      >/dev/null
  fi
  aws iam attach-role-policy --role-name "$role_name" --policy-arn "$policy_arn"
}

ensure_policy_role \
  CoreNovaMarketplaceAssetPublisherRole CoreNovaMarketplaceAssetPublisherPolicy \
  "$IAM_DIR/marketplace-asset-publisher-policy.json" \
  "Publishes immutable EKS Marketplace templates and diagrams only."
ensure_policy_role \
  CoreNovaEksDeliveryE2ERole CoreNovaEksDeliveryE2EPolicy \
  "$IAM_DIR/eks-delivery-e2e-policy.json" \
  "Creates and removes disposable EKS delivery integration-test resources."
aws iam update-role --role-name CoreNovaEksDeliveryE2ERole --max-session-duration 5400

CFN_ROLE=CoreNovaEksDeliveryE2ECloudFormationRole
CFN_POLICY=CoreNovaEksDeliveryE2ECloudFormationPolicy
CFN_POLICY_ARN="arn:aws:iam::${ACCOUNT_ID}:policy/${CFN_POLICY}"
sync_policy "$CFN_POLICY" "$IAM_DIR/eks-delivery-e2e-cloudformation-policy.json" \
  "CloudFormation service permissions for tagged disposable EKS E2E stacks."
if ! aws iam get-role --role-name "$CFN_ROLE" >/dev/null 2>&1; then
  aws iam create-role \
    --role-name "$CFN_ROLE" \
    --description "Service role used only by CoreNova EKS delivery E2E CloudFormation stacks." \
    --permissions-boundary "$CFN_POLICY_ARN" \
    --assume-role-policy-document "file://$IAM_DIR/cloudformation-service-trust-policy.json" \
    --tags Key=Project,Value=builder-ami Key=Product,Value=eks-admin-bastion >/dev/null
else
  aws iam put-role-permissions-boundary --role-name "$CFN_ROLE" --permissions-boundary "$CFN_POLICY_ARN"
fi
aws iam attach-role-policy --role-name "$CFN_ROLE" --policy-arn "$CFN_POLICY_ARN"
ensure_policy_role \
  CoreNovaMarketplaceDeliveryPublisherRole CoreNovaMarketplaceDeliveryPublisherPolicy \
  "$IAM_DIR/marketplace-delivery-publisher-policy.json" \
  "Applies only the guarded dual-architecture EKS AddDeliveryOptions release." \
  "$IAM_DIR/github-marketplace-production-trust-policy.json"
aws iam update-role \
  --role-name CoreNovaMarketplaceDeliveryPublisherRole \
  --max-session-duration 10800

if ! aws s3api head-bucket --bucket "$BUCKET" >/dev/null 2>&1; then
  aws s3api create-bucket --bucket "$BUCKET" --region us-east-1 >/dev/null
fi
aws s3api put-bucket-versioning --bucket "$BUCKET" --versioning-configuration Status=Enabled
aws s3api put-public-access-block \
  --bucket "$BUCKET" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=false,RestrictPublicBuckets=false

BUCKET_POLICY="$(mktemp)"
trap 'rm -f "$BUCKET_POLICY"' EXIT
jq -n --arg bucket "$BUCKET" '{
  Version:"2012-10-17",
  Statement:[
    {Sid:"DenyInsecureTransport",Effect:"Deny",Principal:"*",Action:"s3:*",Resource:[("arn:aws:s3:::"+$bucket),("arn:aws:s3:::"+$bucket+"/*")],Condition:{Bool:{"aws:SecureTransport":"false"}}},
    {Sid:"PublicReadImmutableEksAssets",Effect:"Allow",Principal:"*",Action:"s3:GetObject",Resource:("arn:aws:s3:::"+$bucket+"/eks-admin-bastion/*")}
  ]
}' > "$BUCKET_POLICY"
aws s3api put-bucket-policy --bucket "$BUCKET" --policy "file://$BUCKET_POLICY"
echo "EKS delivery release roles and asset bucket are ready."
