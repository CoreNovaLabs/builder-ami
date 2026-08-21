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
EKS_PRODUCT_IDS = {"prod-hapxotc2y7jmi", "prod-nspz2g6ki6qvo"}
USAGE_INSTRUCTIONS_MAX_LENGTH = 4000


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


def assert_eks_delivery_plan(data: dict) -> None:
    for change in data.get("ChangeSet", []):
        if change.get("ChangeType") != "AddDeliveryOptions":
            continue
        entity_id = (change.get("Entity") or {}).get("Identifier", "").split("@", 1)[0]
        if entity_id not in EKS_PRODUCT_IDS:
            continue
        options = (
            (change.get("DetailsDocument") or {}).get("DeliveryOptions") or []
        )
        if len(options) != 3:
            fail(
                "EKS add-version plans must include standalone AMI, Identity Relay, "
                "and Audited Workstation in the original version request"
            )
        standalone = (
            (options[0].get("Details") or {}).get("AmiDeliveryOptionDetails") or {}
        ).get("AmiSource") or {}
        if not standalone:
            fail("EKS delivery option 1 must be the standalone AMI")
        expected_titles = ("Identity Relay", "Audited Workstation")
        expected_fragments = ("/identity-relay", "/audited-workstation")
        shared_keys = (
            "AmiId",
            "AccessRoleArn",
            "UserName",
            "OperatingSystemName",
            "OperatingSystemVersion",
        )
        for option, title, expected_fragment in zip(
            options[1:], expected_titles, expected_fragments
        ):
            if not str(option.get("DeliveryOptionTitle", "")).startswith(title):
                fail(f"EKS delivery plan is missing the {title} option")
            details = (
                (option.get("Details") or {}).get(
                    "DeploymentTemplateDeliveryOptionDetails"
                )
                or {}
            )
            sources = details.get("TemplateSources") or []
            if len(sources) != 1 or sources[0].get("ParameterName") != "AmiId":
                fail(f"{title} must map the Marketplace AMI to parameter AmiId")
            source = sources[0].get("AmiSource") or {}
            if any(source.get(key) != standalone.get(key) for key in shared_keys):
                fail(f"{title} does not use the same AMI source as standalone delivery")
            for url_field in ("Template", "ArchitectureDiagram"):
                value = str(details.get(url_field, ""))
                if not value.startswith("https://") or "?" in value or "#" in value:
                    fail(f"{title} {url_field} must be a query-free HTTPS URL")
                if expected_fragment not in value:
                    fail(f"{title} {url_field} points to the wrong delivery asset")


def assert_usage_instructions_size(data: dict) -> None:
    for change_index, change in enumerate(data.get("ChangeSet", []), start=1):
        options = (
            (change.get("DetailsDocument") or {}).get("DeliveryOptions") or []
        )
        for option_index, option in enumerate(options, start=1):
            details = option.get("Details") or {}
            for detail_type in (
                "AmiDeliveryOptionDetails",
                "DeploymentTemplateDeliveryOptionDetails",
            ):
                instructions = (details.get(detail_type) or {}).get(
                    "UsageInstructions"
                )
                if instructions is None:
                    continue
                if not isinstance(instructions, str):
                    fail(
                        "UsageInstructions must be a string for "
                        f"change {change_index}, delivery option {option_index}"
                    )
                if len(instructions) > USAGE_INSTRUCTIONS_MAX_LENGTH:
                    fail(
                        "UsageInstructions exceeds the AWS Marketplace Catalog "
                        f"limit for change {change_index}, delivery option "
                        f"{option_index}: {len(instructions)} > "
                        f"{USAGE_INSTRUCTIONS_MAX_LENGTH}"
                    )


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
    assert_eks_delivery_plan(data)
    assert_usage_instructions_size(data)
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
