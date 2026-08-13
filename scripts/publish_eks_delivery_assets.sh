#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source scripts/lib/aws_identity.sh

assert_corenova_assumed_role CoreNovaMarketplaceAssetPublisherRole

BUCKET="${1:?usage: scripts/publish_eks_delivery_assets.sh <bucket> <versioned-prefix>}"
PREFIX="${2:?usage: scripts/publish_eks_delivery_assets.sh <bucket> <versioned-prefix>}"
EXPECTED_BUCKET="corenova-marketplace-assets-582920575154"
if [[ "$BUCKET" != "$EXPECTED_BUCKET" ]]; then
  echo "Unexpected asset bucket: $BUCKET" >&2
  exit 2
fi
if [[ ! "$PREFIX" =~ ^eks-admin-bastion/v[0-9]{8}-[0-9a-f]{12}$ ]]; then
  echo "Asset prefix must be eks-admin-bastion/vYYYYMMDD-COMMITSHA12" >&2
  exit 2
fi
if [[ "$PREFIX" != *"-${GITHUB_SHA:0:12}" ]]; then
  echo "Asset prefix is not bound to GITHUB_SHA" >&2
  exit 2
fi

PACKAGE_DIR="$(mktemp -d)"
trap 'rm -rf "$PACKAGE_DIR"' EXIT
python3 scripts/package_eks_admin_delivery_assets.py --output-dir "$PACKAGE_DIR" >/dev/null

upload_one() {
  local path="$1" relative key digest content_type existing head_file
  relative="${path#"$PACKAGE_DIR"/}"
  key="$PREFIX/$relative"
  digest="$(shasum -a 256 "$path" | awk '{print $1}')"
  head_file="$(mktemp)"
  if aws s3api head-object --bucket "$BUCKET" --key "$key" >"$head_file" 2>/dev/null; then
    existing="$(jq -r '.Metadata.sha256 // empty' "$head_file")"
    rm -f "$head_file"
    if [[ "$existing" != "$digest" ]]; then
      echo "Refusing to overwrite immutable asset s3://$BUCKET/$key" >&2
      return 1
    fi
    echo "UNCHANGED s3://$BUCKET/$key"
    return 0
  fi
  rm -f "$head_file"
  case "$path" in
    *.yaml) content_type=application/yaml ;;
    *.png) content_type=image/png ;;
    *.json) content_type=application/json ;;
    *.md) content_type='text/markdown; charset=utf-8' ;;
    *.html) content_type='text/html; charset=utf-8' ;;
    *.py) content_type='text/x-python; charset=utf-8' ;;
    *) content_type=application/octet-stream ;;
  esac
  aws s3api put-object \
    --bucket "$BUCKET" --key "$key" --body "$path" \
    --content-type "$content_type" \
    --cache-control public,max-age=31536000,immutable \
    --if-none-match '*' \
    --metadata "sha256=$digest,commit=$GITHUB_SHA" >/dev/null
  echo "UPLOADED s3://$BUCKET/$key"
}

while IFS= read -r -d '' path; do
  upload_one "$path"
done < <(find "$PACKAGE_DIR" -type f -print0 | sort -z)

BASE_URL="https://${BUCKET}.s3.amazonaws.com/${PREFIX}"
while IFS= read -r -d '' path; do
  relative="${path#"$PACKAGE_DIR"/}"
  curl --fail --silent --show-error --max-redirs 0 "$BASE_URL/$relative" | cmp - "$path"
done < <(find "$PACKAGE_DIR" -type f -print0 | sort -z)

printf '%s\n' "$BASE_URL"
