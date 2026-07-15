#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from productlib import (
    ROOT,
    assert_marketplace_product,
    product_by_key,
    release_notes,
    run_aws,
    usage_instructions,
    version_title,
)
from render_create_ami_product_changeset import security_groups
from validate_ami import main as validate_main


def validate_ami(product_key: str, ami_id: str) -> None:
    import sys

    old_argv = sys.argv[:]
    try:
        sys.argv = ["validate_ami.py", product_key, ami_id]
        validate_main()
    finally:
        sys.argv = old_argv


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("product_key")
    parser.add_argument("ami_id")
    parser.add_argument("--access-role-arn", required=True)
    parser.add_argument("--source-ami-id")
    parser.add_argument("--output-dir", default=str(ROOT / "plans"))
    args = parser.parse_args()

    product = product_by_key(args.product_key)
    assert_marketplace_product(product)
    validate_ami(args.product_key, args.ami_id)

    change_set = {
        "Catalog": product["_aws"]["marketplace_catalog"],
        "ChangeSet": [
            {
                "ChangeType": "AddDeliveryOptions",
                "Entity": {
                    "Type": "AmiProduct@1.0",
                    "Identifier": product["entity_id"],
                },
                "DetailsDocument": {
                    "Version": {
                        "VersionTitle": version_title(),
                        "ReleaseNotes": release_notes(product, args.ami_id, args.source_ami_id),
                    },
                    "DeliveryOptions": [
                        {
                            "Details": {
                                "AmiDeliveryOptionDetails": {
                                    "AmiSource": {
                                        "AmiId": args.ami_id,
                                        "AccessRoleArn": args.access_role_arn,
                                        "UserName": product["ssh_username"],
                                        "ScanningPort": product["scanning_port"],
                                        "OperatingSystemName": product["operating_system_name"],
                                        "OperatingSystemVersion": product["operating_system_version"],
                                    },
                                    "UsageInstructions": usage_instructions(product, args.ami_id),
                                    "RecommendedInstanceType": product["recommended_instance_type"],
                                    "SecurityGroups": security_groups(product),
                                }
                            }
                        }
                    ],
                },
            }
        ],
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{product['key']}-add-version.json"
    path.write_text(json.dumps(change_set, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
