#!/usr/bin/env bash
set -euo pipefail

CHANGE_SET_ID="${1:?usage: scripts/describe_changeset.sh <change-set-id>}"
aws marketplace-catalog describe-change-set \
  --catalog AWSMarketplace \
  --change-set-id "$CHANGE_SET_ID" \
  --output json
