#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from productlib import (
    ROOT,
    assert_marketplace_product,
    fail,
    product_by_key,
    product_instance_types,
    run_aws,
)


def public_offer(product_id: str) -> dict[str, Any]:
    response = run_aws(
        [
            "marketplace-catalog",
            "list-entities",
            "--catalog",
            "AWSMarketplace",
            "--entity-type",
            "Offer",
            "--filter-list",
            f"Name=ProductId,ValueList={product_id}",
            "--output",
            "json",
        ]
    )
    offers = [
        item
        for item in response.get("EntitySummaryList", [])
        if item.get("Visibility") == "Public"
        and (item.get("OfferSummary") or {}).get("State") == "Released"
    ]
    if len(offers) != 1:
        fail(
            f"expected exactly one released public offer for {product_id}, "
            f"found {len(offers)}"
        )
    offer = run_aws(
        [
            "marketplace-catalog",
            "describe-entity",
            "--catalog",
            "AWSMarketplace",
            "--entity-id",
            offers[0]["EntityId"],
            "--output",
            "json",
        ]
    )
    return {
        "id": offers[0]["EntityId"],
        "details": offer.get("DetailsDocument") or json.loads(offer["Details"]),
    }


def usage_rate_card(offer: dict[str, Any]) -> list[dict[str, str]]:
    terms = [
        term
        for term in offer.get("Terms", [])
        if term.get("Type") == "UsageBasedPricingTerm"
    ]
    if len(terms) != 1:
        fail(f"expected exactly one usage pricing term, found {len(terms)}")
    rate_cards = terms[0].get("RateCards") or []
    if len(rate_cards) != 1 or rate_cards[0].get("Selector"):
        fail("expected one unscoped usage rate card")
    return rate_cards[0].get("RateCard") or []


def validate_instance_types(product: dict[str, Any], instance_types: list[str]) -> None:
    descriptions = run_aws(
        [
            "ec2",
            "describe-instance-types",
            "--instance-types",
            *instance_types,
            "--output",
            "json",
        ]
    )
    described = {
        item["InstanceType"]: item
        for item in descriptions.get("InstanceTypes", [])
    }
    missing = sorted(set(instance_types) - set(described))
    if missing:
        fail(f"EC2 did not describe configured instance types: {missing}")
    incompatible = sorted(
        instance_type
        for instance_type, item in described.items()
        if product["architecture"]
        not in (item.get("ProcessorInfo") or {}).get("SupportedArchitectures", [])
    )
    if incompatible:
        fail(
            f"instance types do not support {product['architecture']}: {incompatible}"
        )
    offerings = run_aws(
        [
            "ec2",
            "describe-instance-type-offerings",
            "--location-type",
            "region",
            "--filters",
            f"Name=location,Values={product['_aws']['region']}",
            "--output",
            "json",
        ]
    )
    offered = {
        item["InstanceType"]
        for item in offerings.get("InstanceTypeOfferings", [])
    }
    unavailable = sorted(set(instance_types) - offered)
    if unavailable:
        fail(
            f"instance types are not offered in {product['_aws']['region']}: "
            f"{unavailable}"
        )


def render(product: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    details = assert_marketplace_product(product)["details"]
    configured = product_instance_types(product)
    if len(configured) != len(set(configured)):
        fail("configured instance_types contains duplicates")
    validate_instance_types(product, configured)

    available = set(
        (details.get("Compatibility") or {}).get("AvailableInstanceTypes") or []
    )
    dimensions = {
        item["Key"] for item in details.get("Dimensions", [])
    }
    if available != dimensions:
        fail(
            "Marketplace compatibility and dimensions differ before the update: "
            f"compatibility_only={sorted(available - dimensions)}, "
            f"dimensions_only={sorted(dimensions - available)}"
        )
    if not available.issubset(configured):
        fail(
            "configured instance_types would remove existing Marketplace support: "
            f"{sorted(available - set(configured))}"
        )

    offer = public_offer(product["entity_id"])
    current_rate_card = usage_rate_card(offer["details"])
    current_prices = {
        item["DimensionKey"]: str(item["Price"])
        for item in current_rate_card
    }
    if set(current_prices) != dimensions:
        fail(
            "Marketplace dimensions and public-offer prices differ before the update: "
            f"unpriced={sorted(dimensions - set(current_prices))}, "
            f"unknown_prices={sorted(set(current_prices) - dimensions)}"
        )

    default_price = str(product["pricing_hourly_usd"])
    configured_prices = {
        instance_type: str(
            (product.get("pricing_by_instance_type") or {}).get(
                instance_type, default_price
            )
        )
        for instance_type in configured
    }
    price_changes = {
        instance_type: {
            "current": current_prices[instance_type],
            "configured": configured_prices[instance_type],
        }
        for instance_type in sorted(available)
        if current_prices[instance_type] != configured_prices[instance_type]
    }
    if price_changes:
        fail(
            "refusing to combine existing price changes with instance additions: "
            f"{price_changes}"
        )

    additions = [item for item in configured if item not in available]
    if not additions:
        fail("no new instance types to add")

    change_set = {
        "Catalog": product["_aws"]["marketplace_catalog"],
        "ChangeSet": [
            {
                "ChangeType": "AddInstanceTypes",
                "Entity": {
                    "Type": "AmiProduct@1.0",
                    "Identifier": product["entity_id"],
                },
                "DetailsDocument": {"InstanceTypes": additions},
            },
            {
                "ChangeType": "AddDimensions",
                "Entity": {
                    "Type": "AmiProduct@1.0",
                    "Identifier": product["entity_id"],
                },
                "DetailsDocument": [
                    {
                        "Name": instance_type,
                        "Description": instance_type,
                        "Key": instance_type,
                        "Unit": "Hrs",
                        "Types": ["Metered"],
                    }
                    for instance_type in additions
                ],
            },
            {
                "ChangeType": "UpdatePricingTerms",
                "Entity": {
                    "Type": "Offer@1.0",
                    "Identifier": offer["id"],
                },
                "DetailsDocument": {
                    "PricingModel": "Usage",
                    "Terms": [
                        {
                            "Type": "UsageBasedPricingTerm",
                            "CurrencyCode": "USD",
                            "RateCards": [
                                {
                                    "RateCard": [
                                        {
                                            "DimensionKey": instance_type,
                                            "Price": configured_prices[instance_type],
                                        }
                                        for instance_type in configured
                                    ]
                                }
                            ],
                        }
                    ],
                },
            },
        ],
    }
    return change_set, additions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("product_key")
    parser.add_argument("--output-dir", default=str(ROOT / "plans"))
    args = parser.parse_args()

    product = product_by_key(args.product_key)
    if product.get("profile") != "eks-admin-bastion":
        fail("this guarded renderer is limited to EKS Admin Bastion products")
    change_set, additions = render(product)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{product['key']}-add-instance-types.json"
    path.write_text(json.dumps(change_set, indent=2) + "\n", encoding="utf-8")
    print(f"{path}: add {', '.join(additions)}")


if __name__ == "__main__":
    main()
