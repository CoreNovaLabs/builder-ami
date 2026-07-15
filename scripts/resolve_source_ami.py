#!/usr/bin/env python3
from __future__ import annotations

from productlib import fail, product_by_key, run_aws


def ami_from_ssm(region: str, parameter: str) -> str:
    return run_aws(
        [
            "ssm",
            "get-parameter",
            "--region",
            region,
            "--name",
            parameter,
            "--query",
            "Parameter.Value",
            "--output",
            "text",
        ],
        json_output=False,
    )


def ami_from_filter(region: str, owner: str, name_pattern: str, architecture: str) -> str:
    if not owner:
        fail("source_ami.owner is not configured; set source_ami.id or owner before building this product")
    data = run_aws(
        [
            "ec2",
            "describe-images",
            "--region",
            region,
            "--owners",
            owner,
            "--filters",
            f"Name=name,Values={name_pattern}",
            f"Name=architecture,Values={architecture}",
            "Name=state,Values=available",
            "--output",
            "json",
        ]
    )
    images = data.get("Images") or []
    if not images:
        fail(f"no source AMI found for owner={owner} name={name_pattern} arch={architecture}")
    images.sort(key=lambda image: image.get("CreationDate", ""))
    return images[-1]["ImageId"]


def resolve(product_key: str) -> str:
    product = product_by_key(product_key)
    region = product["_aws"]["region"]
    source = product.get("source_ami") or {}
    if source.get("id"):
        return source["id"]
    if source.get("ssm_parameter"):
        return ami_from_ssm(region, source["ssm_parameter"])
    return ami_from_filter(region, source.get("owner", ""), source["name_pattern"], product["architecture"])


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("product_key")
    args = parser.parse_args()
    print(resolve(args.product_key))


if __name__ == "__main__":
    main()
