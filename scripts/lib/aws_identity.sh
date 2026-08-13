#!/usr/bin/env bash

assert_corenova_assumed_role() {
  local expected_role="${1:?expected role name is required}"
  local expected_account="${2:-582920575154}"
  local identity account arn

  identity="$(aws sts get-caller-identity --output json)"
  account="$(jq -r '.Account // empty' <<<"$identity")"
  arn="$(jq -r '.Arn // empty' <<<"$identity")"

  if [[ "$account" != "$expected_account" ]]; then
    echo "AWS caller account mismatch: expected $expected_account, got ${account:-unknown}" >&2
    return 1
  fi
  if [[ "$arn" == *":root" ]]; then
    echo "Refusing to run with AWS account root credentials" >&2
    return 1
  fi

  case "$arn" in
    "arn:aws:sts::${expected_account}:assumed-role/${expected_role}/"* | \
      "arn:aws:iam::${expected_account}:role/${expected_role}")
      ;;
    *)
      echo "Expected an assumed $expected_role session; current caller is ${arn:-unknown}" >&2
      return 1
      ;;
  esac
}

assert_corenova_non_root() {
  local expected_account="${1:-582920575154}"
  local identity account arn

  identity="$(aws sts get-caller-identity --output json)"
  account="$(jq -r '.Account // empty' <<<"$identity")"
  arn="$(jq -r '.Arn // empty' <<<"$identity")"

  if [[ "$account" != "$expected_account" ]]; then
    echo "AWS caller account mismatch: expected $expected_account, got ${account:-unknown}" >&2
    return 1
  fi
  if [[ "$arn" == *":root" ]]; then
    echo "Refusing to create a change set with AWS account root credentials" >&2
    return 1
  fi

  echo "AWS caller accepted: $arn" >&2
}
