#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from productlib import (
    ROOT,
    product_by_key,
    product_instance_types,
    release_notes,
    usage_instructions,
    version_title,
)
from validate_ami import main as validate_main


def validate_ami(product_key: str, ami_id: str) -> None:
    import sys

    old_argv = sys.argv[:]
    try:
        sys.argv = ["validate_ami.py", product_key, ami_id]
        validate_main()
    finally:
        sys.argv = old_argv


def product_descriptions(product: dict[str, Any]) -> dict[str, Any]:
    title = product["title"]
    arch_label = "ARM64 / Graviton" if product["architecture"] == "arm64" else "x86_64"
    short = (
        "Replace public SSH jump-host administration for Amazon EKS with a private, "
        "SSM-first workstation in your AWS account. Includes AWS CLI v2, kubectl, "
        "Helm, eksctl, k9s, and IAM/EKS Access Entry examples on Amazon Linux 2023."
    )
    long = f"""Replace public SSH jump-host administration for Amazon EKS with {title}.

CoreNova SSM EKS Admin Bastion is a private, SSM-first administration workstation packaged as an Amazon Machine Image. It runs inside the buyer's AWS account and gives platform engineers, DevOps teams, MSPs, and startup CTOs a controlled host for kubectl, Helm, eksctl, and k9s without maintaining a public SSH jump box or rebuilding each operator workstation.

This is an administration and bastion AMI, not an EKS worker node image. Use it to operate existing or newly created EKS clusters from a private subnet with IAM and Kubernetes RBAC controlled by the buyer.

**Before and after**

- Before: maintain a public or VPN-reachable jump host, install tools repeatedly, and manage version drift across operator laptops.
- After: connect to a standardized private host through AWS Systems Manager Session Manager and keep IAM, EKS Access Entries, and Kubernetes RBAC inside your AWS account.

**What you get**

- Amazon Linux 2023 with CoreNova SSH, audit, logging, time-sync, firewall, and AIDE baseline, current at image build time
- Amazon SSM Agent for managed-node access; operators install AWS CLI v2 and the Session Manager plugin on their own workstation
- SSH key-only fallback with root login and password authentication disabled
- AWS CLI v2 and a multi-version kubectl selector; review the local tool inventory and choose a client compatible with your cluster
- Helm, eksctl, k9s, kubectx, kubens, jq, yq, git, tmux, and troubleshooting utilities
- Starter IAM discovery and EKS Access Entry examples that buyers must review and scope for their environment
- Tool inventory at /etc/corenova/eks-admin-bastion/tool-versions.txt
- Quickstart and examples under /opt/corenova/eks

**Best for**

- Private EKS administration from a controlled EC2 instance
- Replacing public SSH bastion hosts with Session Manager access
- Standardized kubectl and Helm workstation for platform teams
- MSP or consultant access host in customer AWS accounts
- Security-conscious EKS troubleshooting and cluster inspection

**Recommended deployment model**

Launch into a private subnet, attach an IAM role with AmazonSSMManagedInstanceCore and your required EKS access policy, and connect with AWS Systems Manager Session Manager. With SSM connectivity, the instance role, and private-subnet egress in place, no inbound security-group rule is required. The standalone Marketplace launch flow still displays a private TCP 22 fallback recommendation; remove it for SSM-only access or replace it with only your trusted administrator CIDRs.

**Post-launch product check**

Before connecting, install the Session Manager plugin on the operator workstation. Make sure the instance role has an EKS Access Entry (or equivalent legacy `aws-auth` mapping), and make sure the instance can reach the cluster API endpoint on TCP 443.

1. Start a Session Manager shell.
2. Run `corenova-eks-check` to report installed tools and the SSM agent state.
3. Run `aws sts get-caller-identity` to verify the attached role.
4. Run `aws eks update-kubeconfig --region YOUR_REGION --name YOUR_CLUSTER`.
5. Run a read-only check such as `kubectl get nodes` before performing administrative actions.

**Security model**

The AMI ships without hardcoded passwords, private keys, AWS credentials, kubeconfigs, or customer data. Buyers control IAM permissions, EKS Access Entries, Kubernetes RBAC, network access, logging retention, and secrets handling in their own AWS accounts. Anyone who can start a shell on the host can use its EC2 instance-role credentials and inherits that role's EKS permissions. Treat Session Manager access as a trusted-administrator boundary; this AMI does not provide per-user EKS identity isolation.

**Architecture and availability**

{arch_label}. Recommended instance type: {product["recommended_instance_type"]}.

Currently available in us-east-1. See the Pricing tab for the live Marketplace software fee. AWS infrastructure costs such as EC2, EBS, NAT gateway, VPC endpoints, public IPv4, and data transfer are billed separately by AWS.

**Evaluate and deploy**

- Product overview and security boundary: {eks_admin_bastion_url(product)}
- Related architecture: {related_eks_admin_bastion_url(product)}

Support: {product["_aws"].get("support_email", "support@corenovacloud.com")}"""
    return {
        "ProductTitle": title,
        "ShortDescription": short,
        "LongDescription": long,
        "Highlights": [
            "Designed for SSM access: when launched in a private subnet with an instance role and SSM connectivity, no inbound rule is required; SSH remains an optional fallback.",
            "Run inside your AWS account with no baked-in passwords, private keys, AWS credentials, kubeconfigs, or customer data.",
            "Standardize AWS CLI v2, kubectl, Helm, eksctl, k9s, starter IAM/EKS Access Entry examples, a tool inventory, and a local diagnostic command.",
        ],
        "SearchKeywords": product.get("search_keywords")
        or ["eks", "kubectl", "bastion", "al2023", "helm", "eksctl"],
        "Categories": product.get("categories") or ["Operating Systems", "Security"],
        "LogoUrl": product["_aws"].get("logo_url"),
        "AdditionalResources": additional_resources(product),
        "SupportDescription": support_description(product),
    }


def seller_profile_url(product: dict[str, Any]) -> str:
    return product["_aws"].get(
        "seller_profile_url",
        "https://aws.amazon.com/marketplace/seller-profile?id=seller-kbf3ztbtbdc5o",
    )


def amazon_linux_2023_url(product: dict[str, Any]) -> str:
    return product["_aws"].get(
        "related_amazon_linux_2023_url",
        "https://aws.amazon.com/marketplace/pp/prodview-gricbzzlztsae",
    )


def eks_admin_bastion_url(product: dict[str, Any]) -> str:
    return product["_aws"].get(
        "eks_admin_bastion_url",
        "https://www.corenovacloud.com/en/eks-admin-bastion/",
    )


def related_eks_admin_bastion_url(product: dict[str, Any]) -> str:
    if product["architecture"] == "arm64":
        return product["_aws"].get(
            "eks_admin_bastion_x86_url",
            "https://aws.amazon.com/marketplace/pp/prodview-htrkldexsrevo",
        )
    return product["_aws"].get(
        "eks_admin_bastion_arm_url",
        "https://aws.amazon.com/marketplace/pp/prodview-efbisuk5f3bfw",
    )


def additional_resources(product: dict[str, Any]) -> list[dict[str, str]]:
    resources = [
        {
            "Text": "EKS Admin Bastion overview",
            "Url": eks_admin_bastion_url(product),
        },
        {
            "Text": "CoreNova support",
            "Url": product["_aws"].get(
                "support_url", "https://www.corenovacloud.com/en/support/"
            ),
        },
        {
            "Text": "CoreNova security boundaries",
            "Url": product["_aws"].get(
                "security_url", "https://www.corenovacloud.com/en/security/"
            ),
        },
    ]
    return resources


def support_description(product: dict[str, Any]) -> str:
    return f"""Email: {product["_aws"].get("support_email", "support@corenovacloud.com")}

Web: {product["_aws"].get("support_url", "https://www.corenovacloud.com/")}

CoreNova supports AMI launch, AWS Systems Manager Session Manager access, EKS administration tool diagnostics, Marketplace AMI metadata, and documented baseline behavior. Include AWS Region, AMI ID, EC2 Instance ID, instance type, EKS cluster version, tool output, and steps to reproduce.

Refund: {product["_aws"].get("refund_policy", "Eligible requests for a refund of AWS Marketplace software fees may be submitted within 30 days. Live Marketplace offer terms govern. AWS infrastructure charges are excluded and are not refundable by the seller.")}"""


def security_groups(product: dict[str, Any]) -> list[dict[str, Any]]:
    if product.get("profile") == "eks-admin-bastion":
        # The standalone AMI delivery schema requires at least one recommendation.
        # Keep its SSH fallback private; the separate CloudFormation delivery path
        # is the zero-ingress, SSM-first launch model.
        return [
            {
                "IpProtocol": "tcp",
                "IpRanges": [
                    "10.0.0.0/8",
                    "172.16.0.0/12",
                    "192.168.0.0/16",
                ],
                "FromPort": product["scanning_port"],
                "ToPort": product["scanning_port"],
            }
        ]
    return [
        {
            "IpProtocol": "tcp",
            "IpRanges": ["0.0.0.0/0"],
            "FromPort": 22,
            "ToPort": 22,
        }
    ]


def rate_card(product: dict[str, Any]) -> list[dict[str, str]]:
    price = str(product.get("pricing_hourly_usd", "0.04"))
    pricing = product.get("pricing_by_instance_type") or {}
    return [
        {
            "DimensionKey": instance_type,
            "Price": str(pricing.get(instance_type, price)),
        }
        for instance_type in product_instance_types(product)
    ]


def render_change_set(
    product: dict[str, Any],
    ami_id: str,
    access_role_arn: str,
    source_ami_id: str | None,
    public: bool,
) -> dict[str, Any]:
    product_identifier = "$CreateProductChange.Entity.Identifier"
    offer_identifier = "$CreateOfferChange.Entity.Identifier"
    changes: list[dict[str, Any]] = [
        {
            "ChangeType": "CreateProduct",
            "ChangeName": "CreateProductChange",
            "Entity": {"Type": "AmiProduct@1.0"},
            "DetailsDocument": {},
        },
        {
            "ChangeType": "UpdateInformation",
            "Entity": {"Type": "AmiProduct@1.0", "Identifier": product_identifier},
            "DetailsDocument": product_descriptions(product),
        },
        {
            "ChangeType": "AddRegions",
            "Entity": {"Type": "AmiProduct@1.0", "Identifier": product_identifier},
            "DetailsDocument": {"Regions": [product["_aws"]["region"]]},
        },
        {
            "ChangeType": "AddInstanceTypes",
            "Entity": {"Type": "AmiProduct@1.0", "Identifier": product_identifier},
            "DetailsDocument": {"InstanceTypes": product_instance_types(product)},
        },
        {
            "ChangeType": "AddDeliveryOptions",
            "Entity": {"Type": "AmiProduct@1.0", "Identifier": product_identifier},
            "DetailsDocument": {
                "Version": {
                    "VersionTitle": version_title(),
                    "ReleaseNotes": release_notes(product, ami_id, source_ami_id),
                },
                "DeliveryOptions": [
                    {
                        "Details": {
                            "AmiDeliveryOptionDetails": {
                                "AmiSource": {
                                    "AmiId": ami_id,
                                    "AccessRoleArn": access_role_arn,
                                    "UserName": product["ssh_username"],
                                    "ScanningPort": product["scanning_port"],
                                    "OperatingSystemName": product[
                                        "operating_system_name"
                                    ],
                                    "OperatingSystemVersion": product[
                                        "operating_system_version"
                                    ],
                                },
                                "UsageInstructions": usage_instructions(product, ami_id),
                                "RecommendedInstanceType": product[
                                    "recommended_instance_type"
                                ],
                                "SecurityGroups": security_groups(product),
                            }
                        }
                    }
                ],
            },
        },
        {
            "ChangeType": "AddDimensions",
            "Entity": {"Type": "AmiProduct@1.0", "Identifier": product_identifier},
            "DetailsDocument": [
                {
                    "Key": instance_type,
                    "Description": instance_type,
                    "Name": instance_type,
                    "Types": ["Metered"],
                    "Unit": "Hrs",
                }
                for instance_type in product_instance_types(product)
            ],
        },
    ]

    if not public:
        buyer_accounts = product.get("targeting_buyer_accounts") or []
        if buyer_accounts:
            changes.append(
                {
                    "ChangeType": "UpdateTargeting",
                    "Entity": {"Type": "AmiProduct@1.0", "Identifier": product_identifier},
                    "DetailsDocument": {
                        "PositiveTargeting": {"BuyerAccounts": buyer_accounts}
                    },
                }
            )

    changes.extend(
        [
            {
                "ChangeType": "ReleaseProduct",
                "Entity": {"Type": "AmiProduct@1.0", "Identifier": product_identifier},
                "DetailsDocument": {},
            },
            {
                "ChangeType": "CreateOffer",
                "ChangeName": "CreateOfferChange",
                "Entity": {"Type": "Offer@1.0"},
                "DetailsDocument": {"ProductId": product_identifier},
            },
            {
                "ChangeType": "UpdateInformation",
                "Entity": {"Type": "Offer@1.0", "Identifier": offer_identifier},
                "DetailsDocument": {
                    "Name": f"{product['title']} public hourly offer",
                    "Description": f"Public hourly offer for {product['title']}",
                },
            },
            {
                "ChangeType": "UpdatePricingTerms",
                "Entity": {"Type": "Offer@1.0", "Identifier": offer_identifier},
                "DetailsDocument": {
                    "PricingModel": "Usage",
                    "Terms": [
                        {
                            "Type": "UsageBasedPricingTerm",
                            "CurrencyCode": "USD",
                            "RateCards": [{"RateCard": rate_card(product)}],
                        }
                    ],
                },
            },
            {
                "ChangeType": "UpdateLegalTerms",
                "Entity": {"Type": "Offer@1.0", "Identifier": offer_identifier},
                "DetailsDocument": {
                    "Terms": [
                        {
                            "Type": "LegalTerm",
                            "Documents": [
                                {"Type": "StandardEula", "Version": "2022-07-14"}
                            ],
                        }
                    ]
                },
            },
            {
                "ChangeType": "UpdateSupportTerms",
                "Entity": {"Type": "Offer@1.0", "Identifier": offer_identifier},
                "DetailsDocument": {
                    "Terms": [
                        {
                            "Type": "SupportTerm",
                            "RefundPolicy": product["_aws"].get(
                                "refund_policy",
                                "Eligible requests for a refund of AWS Marketplace software fees may be submitted within 30 days. Live Marketplace offer terms govern. AWS infrastructure charges are excluded.",
                            ),
                        }
                    ]
                },
            },
            {
                "ChangeType": "ReleaseOffer",
                "Entity": {"Type": "Offer@1.0", "Identifier": offer_identifier},
                "DetailsDocument": {},
            },
        ]
    )

    return {"Catalog": product["_aws"]["marketplace_catalog"], "ChangeSet": changes}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("product_key")
    parser.add_argument("ami_id")
    parser.add_argument("--access-role-arn", required=True)
    parser.add_argument("--source-ami-id")
    parser.add_argument("--products-file", default=str(ROOT / "products.candidates.yaml"))
    parser.add_argument("--public", action="store_true")
    parser.add_argument("--skip-ami-validation", action="store_true")
    parser.add_argument("--output-dir", default=str(ROOT / "plans" / "new-products"))
    args = parser.parse_args()

    os.environ["CORENOVA_PRODUCTS_FILE"] = args.products_file
    product = product_by_key(args.product_key)
    if not args.skip_ami_validation:
        validate_ami(args.product_key, args.ami_id)

    change_set = render_change_set(
        product,
        args.ami_id,
        args.access_role_arn,
        args.source_ami_id,
        public=args.public,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    visibility = "public" if args.public else "limited"
    path = output_dir / f"{product['key']}-create-{visibility}-hourly.json"
    path.write_text(json.dumps(change_set, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
