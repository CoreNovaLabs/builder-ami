#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml


ACCOUNT_ID = "582920575154"
OBSERVER_ROLE = "CoreNovaMarketplaceObserverRole"
REGION = "us-east-1"
ROOT = Path(__file__).resolve().parents[1]
PRODUCTS_FILE = ROOT / "products.candidates.yaml"


class OpsError(RuntimeError):
    pass


def run_aws(args: list[str]) -> dict[str, Any]:
    env = os.environ.copy()
    env["AWS_PAGER"] = ""
    proc = subprocess.run(
        ["aws", *args, "--output", "json"],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    if proc.returncode:
        message = (proc.stderr or "AWS CLI request failed").strip().splitlines()[-1]
        raise OpsError(f"aws {' '.join(args[:2])}: {message}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise OpsError(f"aws {' '.join(args[:2])}: invalid JSON response") from exc


def assert_observer_identity() -> None:
    identity = run_aws(["sts", "get-caller-identity"])
    account = str(identity.get("Account") or "")
    arn = str(identity.get("Arn") or "")
    if account != ACCOUNT_ID:
        raise OpsError(f"unexpected AWS account {account or 'unknown'}")
    if arn.endswith(":root"):
        raise OpsError("account-root credentials are forbidden")
    marker = f":assumed-role/{OBSERVER_ROLE}/"
    if marker not in arn and not arn.endswith(f":role/{OBSERVER_ROLE}"):
        raise OpsError(f"expected an assumed {OBSERVER_ROLE} session")


def decimal_amount(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except InvalidOperation as exc:
        raise OpsError("Cost Explorer returned an invalid amount") from exc


def first_of_next_month(day: date) -> date:
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


def collect_cost() -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    month_start = today.replace(day=1)
    next_month = first_of_next_month(today)
    actual = Decimal("0")

    if today > month_start:
        response = run_aws(
            [
                "ce",
                "get-cost-and-usage",
                "--time-period",
                f"Start={month_start.isoformat()},End={today.isoformat()}",
                "--granularity",
                "MONTHLY",
                "--metrics",
                "UnblendedCost",
            ]
        )
        periods = response.get("ResultsByTime") or []
        if periods:
            actual = decimal_amount(
                (periods[0].get("Total") or {}).get("UnblendedCost", {}).get("Amount")
            )

    forecast_response = run_aws(
        [
            "ce",
            "get-cost-forecast",
            "--time-period",
            f"Start={today.isoformat()},End={next_month.isoformat()}",
            "--metric",
            "UNBLENDED_COST",
            "--granularity",
            "MONTHLY",
        ]
    )
    remaining = decimal_amount(
        (forecast_response.get("Total") or {}).get("Amount")
    )
    projected = actual + remaining

    if projected >= Decimal("30"):
        level = "INCIDENT"
    elif projected >= Decimal("27"):
        level = "EMERGENCY"
    elif projected >= Decimal("24"):
        level = "FREEZE"
    elif projected >= Decimal("20"):
        level = "WARN"
    else:
        level = "OK"

    return {
        "currency": "USD",
        "month": month_start.strftime("%Y-%m"),
        "actual_to_utc_date": str(actual.quantize(Decimal("0.0001"))),
        "forecast_remaining": str(remaining.quantize(Decimal("0.0001"))),
        "projected_month_total": str(projected.quantize(Decimal("0.0001"))),
        "guard_level": level,
        "thresholds": {
            "warn": "20.00",
            "freeze": "24.00",
            "emergency": "27.00",
            "incident": "30.00",
        },
    }


def count_states(items: list[dict[str, Any]], path: tuple[str, ...]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in items:
        value: Any = item
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        counts[str(value or "unknown")] += 1
    return dict(sorted(counts.items()))


def collect_infrastructure() -> dict[str, Any]:
    instances = run_aws(["ec2", "describe-instances", "--region", REGION])
    instance_items = [
        instance
        for reservation in instances.get("Reservations") or []
        for instance in reservation.get("Instances") or []
    ]
    volumes = run_aws(["ec2", "describe-volumes", "--region", REGION]).get(
        "Volumes"
    ) or []
    snapshots = run_aws(
        ["ec2", "describe-snapshots", "--region", REGION, "--owner-ids", "self"]
    ).get("Snapshots") or []
    addresses = run_aws(["ec2", "describe-addresses", "--region", REGION]).get(
        "Addresses"
    ) or []
    nat_gateways = run_aws(
        ["ec2", "describe-nat-gateways", "--region", REGION]
    ).get("NatGateways") or []
    endpoints = run_aws(
        ["ec2", "describe-vpc-endpoints", "--region", REGION]
    ).get("VpcEndpoints") or []

    return {
        "instances_by_state": count_states(instance_items, ("State", "Name")),
        "volumes_by_state": count_states(volumes, ("State",)),
        "snapshot_count": len(snapshots),
        "snapshot_total_gib": sum(int(item.get("VolumeSize") or 0) for item in snapshots),
        "elastic_ip_count": len(addresses),
        "nat_gateways_by_state": count_states(nat_gateways, ("State",)),
        "vpc_endpoints_by_state": count_states(endpoints, ("State",)),
    }


def load_products() -> list[dict[str, Any]]:
    config = yaml.safe_load(PRODUCTS_FILE.read_text(encoding="utf-8"))
    products = config.get("products") or []
    if {item.get("key") for item in products} != {
        "eks-admin-bastion-al2023-x86_64",
        "eks-admin-bastion-al2023-arm64",
    }:
        raise OpsError("candidate product allowlist changed unexpectedly")
    return products


def details_document(entity: dict[str, Any]) -> dict[str, Any]:
    details = entity.get("DetailsDocument")
    if isinstance(details, dict):
        return details
    legacy = entity.get("Details")
    if isinstance(legacy, str):
        return json.loads(legacy)
    return {}


def collect_marketplace() -> dict[str, Any]:
    summaries: list[dict[str, Any]] = []
    for product in load_products():
        entity_id = str(product["entity_id"])
        entity = run_aws(
            [
                "marketplace-catalog",
                "describe-entity",
                "--region",
                REGION,
                "--catalog",
                "AWSMarketplace",
                "--entity-id",
                entity_id,
            ]
        )
        details = details_document(entity)
        versions = details.get("Versions") or []
        agreement_response = run_aws(
            [
                "marketplace-agreement",
                "search-agreements",
                "--region",
                REGION,
                "--catalog",
                "AWSMarketplace",
                "--filters",
                json.dumps(
                    [
                        {"name": "PartyType", "values": ["Proposer"]},
                        {
                            "name": "ResourceIdentifier",
                            "values": [entity_id],
                        },
                    ]
                ),
                "--max-results",
                "50",
            ]
        )
        agreements = agreement_response.get("agreementViewSummaries") or []
        agreement_states = Counter(
            str(item.get("status") or "unknown") for item in agreements
        )
        images = run_aws(
            [
                "ec2",
                "describe-images",
                "--region",
                REGION,
                "--owners",
                "self",
                "--filters",
                f"Name=tag:ProductKey,Values={product['key']}",
                "Name=state,Values=available",
            ]
        ).get("Images") or []
        images.sort(key=lambda item: str(item.get("CreationDate") or ""), reverse=True)
        latest = images[0] if images else {}
        tags = {
            str(item.get("Key")): str(item.get("Value"))
            for item in latest.get("Tags") or []
        }
        summaries.append(
            {
                "product_key": product["key"],
                "entity_id": entity_id,
                "title_matches_allowlist": (
                    (details.get("Description") or {}).get("ProductTitle")
                    == product["title"]
                ),
                "visibility": details.get("Visibility") or product.get("visibility"),
                "version_count": len(versions),
                "agreement_count": len(agreements),
                "agreements_by_status": dict(sorted(agreement_states.items())),
                "candidate_image_count": len(images),
                "latest_candidate": {
                    "creation_date": latest.get("CreationDate"),
                    "version": tags.get("Version"),
                    "architecture": latest.get("Architecture"),
                }
                if latest
                else None,
            }
        )
    return {"products": summaries}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("all", "cost", "marketplace"), default="all")
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-projected", type=Decimal, default=Decimal("30"))
    args = parser.parse_args()

    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "account_id": ACCOUNT_ID,
        "errors": [],
    }
    exit_code = 0
    try:
        assert_observer_identity()
        if args.mode in {"all", "cost"}:
            report["cost"] = collect_cost()
            report["infrastructure"] = collect_infrastructure()
            projected = Decimal(report["cost"]["projected_month_total"])
            level = report["cost"]["guard_level"]
            print(f"COST_GUARD {level} projected_usd={projected}")
            if projected >= Decimal("20"):
                print(f"::warning::AWS monthly projection is ${projected} ({level})")
            if projected >= args.max_projected:
                report["errors"].append(
                    f"projected AWS cost {projected} reached workflow ceiling {args.max_projected}"
                )
                exit_code = 3
        if args.mode in {"all", "marketplace"}:
            report["marketplace"] = collect_marketplace()
            for product in report["marketplace"]["products"]:
                print(
                    "MARKETPLACE_HEALTH"
                    f" product={product['product_key']}"
                    f" agreements={product['agreement_count']}"
                    f" candidate_images={product['candidate_image_count']}"
                    f" title_match={str(product['title_matches_allowlist']).lower()}"
                )
    except (OpsError, json.JSONDecodeError, OSError) as exc:
        report["errors"].append(str(exc))
        print(f"OPS_MONITOR_ERROR {exc}", file=sys.stderr)
        exit_code = 1
    finally:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
