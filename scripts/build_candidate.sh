#!/usr/bin/env bash
set -euo pipefail

PRODUCT_KEY="${1:?usage: scripts/build_candidate.sh <candidate-product-key>}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
cd "$ROOT_DIR"
source scripts/lib/aws_identity.sh

export CORENOVA_PRODUCTS_FILE="${CORENOVA_PRODUCTS_FILE:-products.candidates.yaml}"

assert_corenova_assumed_role CoreNovaAmiBuilderRole

SOURCE_AMI_ID="$("$PYTHON_BIN" scripts/resolve_source_ami.py "$PRODUCT_KEY")"
VERSION_TITLE="v$(date -u +%Y%m%d)"
VARS_FILE="build/${PRODUCT_KEY}.auto.pkrvars.hcl"
mkdir -p build artifacts logs

"$PYTHON_BIN" scripts/write_packer_vars.py "$PRODUCT_KEY" "$SOURCE_AMI_ID" "$VERSION_TITLE" "$VARS_FILE"

echo "Building candidate $PRODUCT_KEY from $SOURCE_AMI_ID as $VERSION_TITLE"
packer init packer/marketplace-ami.pkr.hcl
packer build -var-file="$VARS_FILE" -machine-readable packer/marketplace-ami.pkr.hcl | tee "logs/${PRODUCT_KEY}-${VERSION_TITLE}.log"

AMI_ID="$(awk -F, '/artifact,0,id/ {print $NF}' "logs/${PRODUCT_KEY}-${VERSION_TITLE}.log" | awk -F: '{print $NF}' | tail -1)"
if [[ -z "$AMI_ID" ]]; then
  echo "Unable to parse AMI ID from Packer log" >&2
  exit 1
fi

"$PYTHON_BIN" scripts/validate_ami.py "$PRODUCT_KEY" "$AMI_ID"
printf '%s\n' "$AMI_ID" > "artifacts/${PRODUCT_KEY}-${VERSION_TITLE}.ami_id"
printf '%s\n' "$SOURCE_AMI_ID" > "artifacts/${PRODUCT_KEY}-${VERSION_TITLE}.source_ami_id"
echo "$AMI_ID"
