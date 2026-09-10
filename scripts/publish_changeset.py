#!/usr/bin/env python3
"""Apply one already-validated AddDeliveryOptions plan for a rebuilt AMI product.

Guarded publisher path for the marketplace-rebuild factory: the plan must
target a products.yaml entity, contain only AddDeliveryOptions changes, and
be submitted from an assumed CoreNovaMarketplaceDeliveryPublisherRole
session. The role's IAM policy independently restricts StartChangeSet to
APPLY intent and AddDeliveryOptions change types for allowlisted products.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from productlib import PRODUCTS_FILE_ENV, fail, load_config
from submit_changeset import (
    assert_allowed_change_set,
    assert_eks_delivery_plan,
    assert_usage_instructions_size,
)

PUBLISHER_ROLE_NAME = "CoreNovaMarketplaceDeliveryPublisherRole"


def assert_expected_caller(expected_account_id: str) -> None:
    try:
        output = subprocess.check_output(
            ["aws", "sts", "get-caller-identity", "--output", "json"],
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        fail(f"could not verify the AWS caller identity: {exc}")

    identity = json.loads(output)
    account_id = identity.get("Account")
    arn = identity.get("Arn", "")
    if account_id != expected_account_id:
        fail(
            "AWS caller account mismatch: "
            f"expected {expected_account_id}, got {account_id or 'unknown'}"
        )
    if arn.endswith(":root"):
        fail("refusing to call StartChangeSet with AWS account root credentials")
    assumed_role_marker = f":assumed-role/{PUBLISHER_ROLE_NAME}/"
    direct_role_suffix = f":role/{PUBLISHER_ROLE_NAME}"
    if assumed_role_marker not in arn and not arn.endswith(direct_role_suffix):
        fail(
            f"APPLY requires an assumed {PUBLISHER_ROLE_NAME} session; "
            f"current caller is {arn or 'unknown'}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan")
    parser.add_argument("--confirm-apply", action="store_true")
    parser.add_argument("--products-file")
    args = parser.parse_args()

    if args.products_file:
        os.environ[PRODUCTS_FILE_ENV] = args.products_file

    path = Path(args.plan)
    data = assert_allowed_change_set(path)
    assert_eks_delivery_plan(data)
    assert_usage_instructions_size(data)
    changes = data.get("ChangeSet") or []
    if not changes:
        fail("change set must contain at least one change")
    if {change.get("ChangeType") for change in changes} != {"AddDeliveryOptions"}:
        fail(
            "the guarded marketplace publish path only supports "
            "AddDeliveryOptions for one rebuilt AMI version"
        )

    if not args.confirm_apply:
        fail("APPLY requires --confirm-apply")

    config = load_config()
    assert_expected_caller(str(config["aws"]["seller_account_id"]))

    cmd = [
        "aws",
        "marketplace-catalog",
        "start-change-set",
        "--catalog",
        data["Catalog"],
        "--change-set",
        json.dumps(data["ChangeSet"]),
        "--intent",
        "APPLY",
        "--output",
        "json",
    ]
    print(" ".join(cmd[:5] + ["..."]), file=sys.stderr)
    subprocess.check_call(cmd)


if __name__ == "__main__":
    main()
