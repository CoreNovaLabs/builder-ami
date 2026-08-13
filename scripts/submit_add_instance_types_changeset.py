#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from decimal import Decimal
from pathlib import Path
from typing import Any

from productlib import (
    PRODUCTS_FILE_ENV,
    assert_marketplace_product,
    fail,
    load_config,
    product_by_key,
    product_instance_types,
)
from render_add_instance_types_changeset import public_offer, usage_rate_card


PUBLISHER_ROLE_NAME = "CoreNovaMarketplaceInstancePublisherRole"
EXPECTED_OFFERS = {
    "prod-hapxotc2y7jmi": "offer-2izpqagw3tftq",
    "prod-nspz2g6ki6qvo": "offer-2n3inrntp75ye",
}


def assert_expected_caller(expected_account_id: str) -> dict[str, Any]:
    identity = json.loads(
        subprocess.check_output(
            ["aws", "sts", "get-caller-identity", "--output", "json"],
            text=True,
        )
    )
    arn = identity.get("Arn", "")
    if identity.get("Account") != expected_account_id:
        fail(f"AWS caller account mismatch: {identity.get('Account') or 'unknown'}")
    if f":assumed-role/{PUBLISHER_ROLE_NAME}/" not in arn:
        fail(f"APPLY requires an assumed {PUBLISHER_ROLE_NAME} session; got {arn}")
    return identity


def normalized_price(value: str) -> Decimal:
    try:
        return Decimal(value)
    except Exception as exc:
        fail(f"invalid price {value!r}: {exc}")


def validate_plan(path: Path, product_key: str) -> dict[str, Any]:
    product = product_by_key(product_key)
    product_id = product["entity_id"]
    expected_offer = EXPECTED_OFFERS.get(product_id)
    if not expected_offer:
        fail(f"product {product_id} has no guarded offer mapping")

    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("Catalog") != product["_aws"]["marketplace_catalog"]:
        fail("unexpected Marketplace catalog")
    changes = data.get("ChangeSet") or []
    if [item.get("ChangeType") for item in changes] != [
        "AddInstanceTypes",
        "AddDimensions",
        "UpdatePricingTerms",
    ]:
        fail("plan must contain exactly AddInstanceTypes, AddDimensions, UpdatePricingTerms")

    product_entities = [changes[0]["Entity"], changes[1]["Entity"]]
    if any(
        entity != {"Type": "AmiProduct@1.0", "Identifier": product_id}
        for entity in product_entities
    ):
        fail("instance and dimension changes do not target the selected product")
    if changes[2]["Entity"] != {
        "Type": "Offer@1.0",
        "Identifier": expected_offer,
    }:
        fail("pricing change does not target the guarded public offer")

    details = assert_marketplace_product(product)["details"]
    current_instances = set(
        (details.get("Compatibility") or {}).get("AvailableInstanceTypes") or []
    )
    configured_instances = product_instance_types(product)
    expected_additions = [
        item for item in configured_instances if item not in current_instances
    ]
    if changes[0].get("DetailsDocument") != {"InstanceTypes": expected_additions}:
        fail("AddInstanceTypes does not equal the live-to-configured delta")

    dimensions = changes[1].get("DetailsDocument") or []
    dimension_keys = [item.get("Key") for item in dimensions]
    if dimension_keys != expected_additions:
        fail("AddDimensions does not exactly match the instance additions")
    for item in dimensions:
        key = item["Key"]
        if item != {
            "Name": key,
            "Description": key,
            "Key": key,
            "Unit": "Hrs",
            "Types": ["Metered"],
        }:
            fail(f"unexpected dimension definition for {key}")

    offer = public_offer(product_id)
    if offer["id"] != expected_offer:
        fail("live public offer does not match the guarded offer mapping")
    current_prices = {
        item["DimensionKey"]: normalized_price(str(item["Price"]))
        for item in usage_rate_card(offer["details"])
    }
    expected_price = normalized_price(str(product["pricing_hourly_usd"]))
    for instance_type in current_instances:
        if current_prices.get(instance_type) != expected_price:
            fail(f"existing price drift for {instance_type}")

    pricing = changes[2].get("DetailsDocument") or {}
    if pricing.get("PricingModel") != "Usage":
        fail("pricing model must remain Usage")
    terms = pricing.get("Terms") or []
    if len(terms) != 1 or terms[0].get("Type") != "UsageBasedPricingTerm":
        fail("expected one usage-based pricing term")
    if terms[0].get("CurrencyCode") != "USD":
        fail("currency must remain USD")
    rate_cards = terms[0].get("RateCards") or []
    if len(rate_cards) != 1 or set(rate_cards[0]) != {"RateCard"}:
        fail("expected one unscoped rate card")
    planned_rates = rate_cards[0]["RateCard"]
    if [item.get("DimensionKey") for item in planned_rates] != configured_instances:
        fail("rate card does not cover the configured instances in order")
    if any(normalized_price(str(item.get("Price"))) != expected_price for item in planned_rates):
        fail("all planned prices must equal the configured hourly price")
    if not expected_additions:
        fail("no new instance types remain to publish")
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("product_key")
    parser.add_argument("plan")
    parser.add_argument("--products-file", default="products.candidates.yaml")
    parser.add_argument("--confirm-apply", action="store_true")
    args = parser.parse_args()

    if not args.confirm_apply:
        fail("APPLY requires --confirm-apply")
    os.environ[PRODUCTS_FILE_ENV] = args.products_file
    config = load_config()
    data = validate_plan(Path(args.plan), args.product_key)
    assert_expected_caller(str(config["aws"]["seller_account_id"]))

    result = subprocess.check_output(
        [
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
        ],
        text=True,
    )
    print(result, end="")


if __name__ == "__main__":
    main()
