#!/usr/bin/env python3
from __future__ import annotations

from productlib import fail, product_by_key, run_aws


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("product_key")
    parser.add_argument("ami_id")
    args = parser.parse_args()

    product = product_by_key(args.product_key)
    region = product["_aws"]["region"]
    account_id = product["_aws"]["seller_account_id"]

    data = run_aws(
        [
            "ec2",
            "describe-images",
            "--region",
            region,
            "--image-ids",
            args.ami_id,
            "--output",
            "json",
        ]
    )
    images = data.get("Images") or []
    if len(images) != 1:
        fail(f"expected exactly one AMI for {args.ami_id}, found {len(images)}")
    image = images[0]

    checks = {
        "OwnerId": image.get("OwnerId") == account_id,
        "Architecture": image.get("Architecture") == product["architecture"],
        "VirtualizationType": image.get("VirtualizationType") == "hvm",
        "RootDeviceType": image.get("RootDeviceType") == "ebs",
        "ImageType": image.get("ImageType") == "machine",
        "State": image.get("State") == "available",
        "NoProductCodes": not image.get("ProductCodes"),
        "EnaSupport": bool(image.get("EnaSupport")),
    }

    for mapping in image.get("BlockDeviceMappings") or []:
        ebs = mapping.get("Ebs")
        if not ebs:
            continue
        checks[f"SnapshotUnencrypted:{mapping.get('DeviceName')}"] = ebs.get("Encrypted") is False

    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"{'OK' if ok else 'FAIL'}\t{name}")
    if failed:
        fail("AMI validation failed: " + ", ".join(failed))
    print(f"VALID\t{args.ami_id}\t{product['key']}")


if __name__ == "__main__":
    main()
