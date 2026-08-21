#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

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


def ami_source(product: dict, ami_id: str, access_role_arn: str) -> dict:
    return {
        "AmiId": ami_id,
        "AccessRoleArn": access_role_arn,
        "UserName": product["ssh_username"],
        "ScanningPort": product["scanning_port"],
        "OperatingSystemName": product["operating_system_name"],
        "OperatingSystemVersion": product["operating_system_version"],
    }


def deployment_template_ami_source(source: dict) -> dict:
    """Return the fields accepted by DeploymentTemplate TemplateSources."""
    return {key: value for key, value in source.items() if key != "ScanningPort"}


def validate_asset_base_url(value: str) -> str:
    base = value.rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("asset base URL must be a query-free HTTPS URL")
    return base


def eks_cloudformation_delivery_options(
    product: dict, source: dict, asset_base_url: str
) -> list[dict]:
    base = validate_asset_base_url(asset_base_url)
    architecture = product["architecture"]
    if architecture not in {"x86_64", "arm64"}:
        raise ValueError(f"unsupported EKS delivery architecture: {architecture}")
    asset_path = f"{base}/{architecture}"
    template_source = deployment_template_ami_source(source)
    identity_usage = (
        "Launch in a private subnet with SSM connectivity. After CREATE_COMPLETE, "
        f"download the versioned client from {base}/client/corenova_eks_connect.py "
        "and run "
        "the ConnectCommand stack output. kubectl tokens are generated from the "
        "operator's local AWS identity; the relay EC2 role has no EKS permissions."
        f" Buyer guide: {base}/docs/index.html"
    )
    audited_usage = (
        "Launch in a private subnet with SSM connectivity. Use the "
        "StartSessionCommand stack output so the product-specific session document "
        "enables Run As and CloudWatch streaming. Then run corenova-eks-doctor and "
        "a read-only kubectl authorization check before operational commands."
        f" Buyer guide: {base}/docs/index.html"
    )
    return [
        {
            "DeliveryOptionTitle": "Identity Relay - per-user AWS identity",
            "Details": {
                "DeploymentTemplateDeliveryOptionDetails": {
                    "ShortDescription": (
                        "Private EKS API relay with zero ingress and no EKS permissions "
                        "on the EC2 role."
                    ),
                    "LongDescription": (
                        "Deploys one private EC2 relay managed through AWS Systems "
                        "Manager. Operators forward a local port to the private EKS API "
                        "and authenticate with their own AWS role, preserving per-user "
                        "EKS access entries and CloudTrail identity. The instance has no "
                        "public IPv4 address, no inbound security-group rules, an "
                        "encrypted gp3 root volume, and IMDSv2-only metadata. Optional "
                        "resources can add the cluster security-group rule and a scoped "
                        "EKS access entry for the operator role. Session Manager cannot "
                        "log the contents of port-forwarding sessions."
                    ),
                    "UsageInstructions": identity_usage,
                    "RecommendedInstanceType": product["recommended_instance_type"],
                    "ArchitectureDiagram": f"{asset_path}/identity-relay-architecture.png",
                    "Template": f"{asset_path}/identity-relay.yaml",
                    "TemplateSources": [
                        {
                            "ParameterName": "AmiId",
                            "AmiSource": template_source,
                        }
                    ],
                }
            },
        },
        {
            "DeliveryOptionTitle": "Audited Workstation - streamed shell logs",
            "Details": {
                "DeploymentTemplateDeliveryOptionDetails": {
                    "ShortDescription": (
                        "Private EKS workstation with a Run As shell and retained "
                        "CloudWatch session logs."
                    ),
                    "LongDescription": (
                        "Deploys one private EKS administration workstation managed "
                        "through AWS Systems Manager. A product-specific session document "
                        "runs shells as the non-root corenova-operator user, streams shell "
                        "activity to a retained CloudWatch Logs group, and enforces idle "
                        "and maximum session durations. The default EKS access is View in "
                        "the default namespace. Edit or administrator access requires an "
                        "explicit acknowledgement because all users who can start a shell "
                        "share the EC2 role. The instance has no public IPv4 address, no "
                        "inbound rules, encrypted gp3 storage, and IMDSv2-only metadata."
                    ),
                    "UsageInstructions": audited_usage,
                    "RecommendedInstanceType": product["recommended_instance_type"],
                    "ArchitectureDiagram": f"{asset_path}/audited-workstation-architecture.png",
                    "Template": f"{asset_path}/audited-workstation.yaml",
                    "TemplateSources": [
                        {
                            "ParameterName": "AmiId",
                            "AmiSource": template_source,
                        }
                    ],
                }
            },
        },
    ]


def build_change_set(
    *,
    product: dict,
    ami_id: str,
    access_role_arn: str,
    source_ami_id: str | None = None,
    include_eks_cloudformation: bool = False,
    asset_base_url: str | None = None,
    version_title_override: str | None = None,
) -> dict:
    if include_eks_cloudformation and product.get("profile") != "eks-admin-bastion":
        raise ValueError("CloudFormation delivery options require the eks-admin-bastion profile")
    if include_eks_cloudformation and not asset_base_url:
        raise ValueError("asset_base_url is required for CloudFormation delivery options")
    if asset_base_url and not include_eks_cloudformation:
        raise ValueError("asset_base_url requires CloudFormation delivery options")
    selected_version = version_title_override or version_title()
    if not selected_version.startswith("v") or not selected_version[1:].isdigit() or len(selected_version) != 9:
        raise ValueError("version title must use vYYYYMMDD")

    source = ami_source(product, ami_id, access_role_arn)
    if include_eks_cloudformation:
        # AWS Marketplace requires every delivery option in one AMI version to
        # use the exact same AmiSource object. ScanningPort is accepted only by
        # standalone AMI delivery and defaults to 22, so omit it from all three
        # options when CloudFormation delivery is included.
        source = deployment_template_ami_source(source)
    delivery_options = [
        {
            "Details": {
                "AmiDeliveryOptionDetails": {
                    "AmiSource": source,
                    "UsageInstructions": usage_instructions(product, ami_id),
                    "RecommendedInstanceType": product["recommended_instance_type"],
                    "SecurityGroups": security_groups(product),
                }
            }
        }
    ]
    if include_eks_cloudformation:
        assert asset_base_url is not None
        delivery_options.extend(
            eks_cloudformation_delivery_options(product, source, asset_base_url)
        )
    return {
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
                        "VersionTitle": selected_version,
                        "ReleaseNotes": release_notes(
                            product, ami_id, source_ami_id, selected_version
                        ),
                    },
                    "DeliveryOptions": delivery_options,
                },
            }
        ],
    }


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
    parser.add_argument(
        "--include-eks-cloudformation",
        action="store_true",
        help="add the Identity Relay and Audited Workstation delivery options",
    )
    parser.add_argument(
        "--asset-base-url",
        help="public HTTPS base URL containing the EKS CloudFormation delivery assets",
    )
    parser.add_argument(
        "--version-title",
        help="fixed release title in vYYYYMMDD format",
    )
    args = parser.parse_args()

    product = product_by_key(args.product_key)
    assert_marketplace_product(product)
    validate_ami(args.product_key, args.ami_id)

    if args.include_eks_cloudformation and product.get("profile") != "eks-admin-bastion":
        parser.error("--include-eks-cloudformation is only valid for EKS bastion products")
    if args.include_eks_cloudformation and not args.asset_base_url:
        parser.error("--asset-base-url is required with --include-eks-cloudformation")
    if args.asset_base_url and not args.include_eks_cloudformation:
        parser.error("--asset-base-url requires --include-eks-cloudformation")

    change_set = build_change_set(
        product=product,
        ami_id=args.ami_id,
        access_role_arn=args.access_role_arn,
        source_ami_id=args.source_ami_id,
        include_eks_cloudformation=args.include_eks_cloudformation,
        asset_base_url=args.asset_base_url,
        version_title_override=args.version_title,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{product['key']}-add-version.json"
    path.write_text(json.dumps(change_set, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
