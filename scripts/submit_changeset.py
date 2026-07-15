#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from productlib import PRODUCTS_FILE_ENV, fail, load_config


VALIDATOR_ROLE_NAME = "CoreNovaMarketplaceValidatorRole"
PUBLISHER_ROLE_NAME = "CoreNovaMarketplacePublisherRole"


def assert_expected_caller(intent: str, expected_account_id: str) -> dict:
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

    expected_role = (
        VALIDATOR_ROLE_NAME if intent == "VALIDATE" else PUBLISHER_ROLE_NAME
    )
    assumed_role_marker = f":assumed-role/{expected_role}/"
    direct_role_suffix = f":role/{expected_role}"
    if assumed_role_marker not in arn and not arn.endswith(direct_role_suffix):
        fail(
            f"{intent} requires an assumed {expected_role} session; "
            f"current caller is {arn or 'unknown'}"
        )
    return identity


def assert_allowed_change_set(path: Path, *, allow_new_products: bool = False) -> dict:
    config = load_config()
    allowed = {(p["entity_id"], p["title"]) for p in config["products"]}
    allowed_ids = {entity_id for entity_id, _ in allowed}
    data = json.loads(path.read_text(encoding="utf-8"))
    creates_new_product = any(
        change.get("ChangeType") == "CreateProduct"
        and (change.get("Entity") or {}).get("Type") == "AmiProduct@1.0"
        for change in data.get("ChangeSet", [])
    )
    allowed_change_types = {
        "AddDeliveryOptions",
        "RestrictDeliveryOptions",
        "UpdateDeliveryOptions",
        "UpdateInformation",
        "UpdateVisibility",
    }
    if allow_new_products:
        allowed_change_types.update(
            {
                "CreateProduct",
                "AddRegions",
                "AddInstanceTypes",
                "AddDimensions",
                "UpdateTargeting",
                "ReleaseProduct",
                "CreateOffer",
                "UpdatePricingTerms",
                "UpdateLegalTerms",
                "UpdateSupportTerms",
                "ReleaseOffer",
            }
        )
    for change in data.get("ChangeSet", []):
        entity = change.get("Entity") or {}
        identifier = entity.get("Identifier", "").split("@", 1)[0]
        if (
            not identifier
            and allow_new_products
            and change.get("ChangeType") in {"CreateProduct", "CreateOffer"}
        ):
            pass
        elif identifier.startswith("$CreateProductChange") or identifier.startswith(
            "$CreateOfferChange"
        ):
            if not allow_new_products or not creates_new_product:
                fail(f"change set references generated entity {identifier}")
        elif entity.get("Type") == "AmiProduct@1.0" and identifier not in allowed_ids:
            fail(f"change set targets non-allowlisted product {identifier}")
        if change.get("ChangeType") not in allowed_change_types:
            fail(f"unsupported change type {change.get('ChangeType')}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan")
    parser.add_argument("--intent", choices=["VALIDATE", "APPLY"], default="VALIDATE")
    parser.add_argument("--confirm-apply", action="store_true")
    parser.add_argument("--allow-new-products", action="store_true")
    parser.add_argument("--products-file")
    args = parser.parse_args()

    if args.products_file:
        os.environ[PRODUCTS_FILE_ENV] = args.products_file

    path = Path(args.plan)
    data = assert_allowed_change_set(path, allow_new_products=args.allow_new_products)
    changes = data.get("ChangeSet", [])
    if not changes:
        fail("change set must contain at least one change")
    change_types = {change.get("ChangeType") for change in changes}

    if args.intent == "VALIDATE" and change_types != {"AddDeliveryOptions"}:
        fail(
            "the guarded VALIDATE workflow only supports AddDeliveryOptions "
            "for a new single-AMI version"
        )
    if args.intent == "APPLY" and not args.confirm_apply:
        fail("APPLY requires --confirm-apply")
    if args.intent == "APPLY":
        if change_types != {"UpdateInformation"}:
            fail(
                "the guarded APPLY workflow only supports UpdateInformation; "
                "release, delivery, pricing, and visibility changes require a "
                "separate reviewed publisher workflow"
            )

    config = load_config()
    assert_expected_caller(args.intent, str(config["aws"]["seller_account_id"]))

    cmd = [
        "aws",
        "marketplace-catalog",
        "start-change-set",
        "--catalog",
        data["Catalog"],
        "--change-set",
        json.dumps(data["ChangeSet"]),
        "--intent",
        args.intent,
        "--output",
        "json",
    ]
    print(" ".join(cmd[:5] + ["..."]), file=sys.stderr)
    subprocess.check_call(cmd)


if __name__ == "__main__":
    main()
