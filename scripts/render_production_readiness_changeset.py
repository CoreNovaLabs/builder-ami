#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from productlib import (
    ROOT,
    assert_marketplace_product,
    latest_version,
    product_by_key,
)


def storage_description(product: dict[str, Any]) -> str:
    layout = product["layout"]
    if product["key"] == "amazon-linux-2023-arm64-64k":
        return "Ext4 root volume with Amazon Linux 2023 ARM64 64K-page kernel support."
    if layout == "lvm-xfs":
        return "LVM with XFS. The layout separates operating-system paths used by logs and temporary data."
    if layout == "lvm":
        return "LVM-backed storage layout for operating-system and workload data."
    return "Standard Ext4 root volume."


def feature_bullets(product: dict[str, Any]) -> list[str]:
    bullets = [
        f"SSH key-only access with root login disabled; default user: {product['ssh_username']}.",
        "Host firewall enabled with SSH available for administrator access.",
        "auditd, rsyslog, chrony, and AIDE configured during image build.",
        "Automatic security updates enabled where supported by the operating system.",
        "OpenSCAP profile information included for buyer-side validation.",
    ]
    if product["key"] == "amazon-linux-2023-arm64-64k":
        bullets.extend(
            [
                "SELinux enforcing mode.",
                "Amazon Linux 2023 ARM64 64K-page kernel support.",
            ]
        )
    if product["layout"].startswith("lvm"):
        bullets.append("corenova-lvm-grow.service included for online volume growth.")
    return bullets


def short_description(product: dict[str, Any]) -> str:
    return (
        f"{product['title']}: hardened EC2 AMI for production use. Includes "
        "SSH key-only access, firewall baseline, audit logging, AIDE, automatic "
        "security updates where supported, and OpenSCAP validation notes. By "
        "CoreNova Intelligence Limited."
    )


def long_description(product: dict[str, Any]) -> str:
    bullets = "\n".join(f"- {line}" for line in feature_bullets(product))
    return f"""{product["title"]} is a hardened EC2 AMI for teams that want a repeatable {product["operating_system_version"]} baseline on AWS.

The AMI is built by CoreNova Intelligence Limited for production use. It does not expire and does not disable features based on time, user count, or instance count. AWS Marketplace offer terms affect billing only; they do not change the AMI functionality.

**Included baseline**

{bullets}

**Use cases**

- Bastion hosts and jump boxes with SSH key-only administration.
- Application servers that need a documented hardened OS baseline.
- Security-sensitive workloads standardized on {product["operating_system_version"]}.
- Platform teams that want consistent EC2 launch behavior.

**Storage and architecture**

{storage_description(product)}

Architecture: {product["architecture"]}.
Recommended instance type: {product["recommended_instance_type"]}.

**Security and compliance**

Hardening follows CIS Benchmark guidance with OpenSCAP profile information where available. This product is not an official CIS-certified image. Buyers should run their own validation and apply organization-specific controls for regulatory requirements.

**Requirements**

- Launch from AWS Marketplace in us-east-1.
- EC2 key pair required; SSH password authentication is disabled.
- Security group should allow TCP 22 only from trusted administrator networks.
- AWS Marketplace software charges follow the offer terms shown at subscription time. EC2 infrastructure charges are billed separately by AWS.

**Support**

Email: support@corenovacloud.com
Web: https://www.corenovacloud.com/

Include AWS Region, AMI ID, EC2 Instance ID, instance type, and steps to reproduce when opening a support request."""


def support_description() -> str:
    return """Email: support@corenovacloud.com

Web: https://www.corenovacloud.com/

CoreNova supports launch, SSH access, baseline service checks, Marketplace AMI metadata, and documented hardening behavior. Include AWS Region, AMI ID, EC2 Instance ID, instance type, and steps to reproduce.

Refund: 30-day refund on Marketplace software fees. EC2 infrastructure charges are billed by AWS and are not refundable by the seller."""


def usage_instructions(product: dict[str, Any], ami_id: str) -> str:
    checks = [
        "systemctl is-active rsyslog",
        "systemctl is-active chronyd || systemctl is-active chrony",
        "sudo sshd -T | grep -E 'permitrootlogin|passwordauthentication'",
    ]
    if product["operating_system_name"] in {"AMAZONLINUX", "CENTOS", "OTHERLINUX"}:
        checks.append("sudo systemctl is-active firewalld")
    if product["layout"].startswith("lvm"):
        checks.extend(["sudo lvs", "findmnt /tmp /var /home || true"])
    check_block = "\n".join(checks)

    return f"""**Overview**

{product["title"]} is a hardened EC2 AMI built by CoreNova Intelligence Limited for production use. The AMI does not expire and does not disable features based on time, user count, or instance count.

Recommended instance type: {product["recommended_instance_type"]}.
AMI: {ami_id} (us-east-1).

**Launch checklist**

1. Subscribe in AWS Marketplace, then launch in us-east-1.
2. Select an instance type compatible with {product["architecture"]}.
3. Select your EC2 SSH key pair. Password login is disabled.
4. Restrict inbound TCP 22 to trusted administrator IP ranges.
5. Review EC2 instance, EBS, data transfer, and AWS Marketplace software charges before launch.

**First connection**

ssh -i your-key.pem {product["ssh_username"]}@YOUR_PUBLIC_IP

**Post-launch health verification**

{check_block}

Expected SSH settings:
permitrootlogin no
passwordauthentication no

Also verify EC2 instance status checks in the Amazon EC2 console.

**Sensitive data and credentials**

The AMI does not include hardcoded passwords, private keys, AWS credentials, or customer data. Customer-created keys and workload data remain in the buyer's AWS account. Linux system logs are stored under /var/log unless the buyer changes operating-system defaults.

**Encryption**

The Marketplace source AMI uses unencrypted EBS snapshots as required for AWS Marketplace AMI ingestion. Buyers can launch or copy the AMI with encrypted EBS volumes according to their own AWS account policy.

**Service quotas and costs**

This AMI uses standard EC2, EBS, networking, and AWS Marketplace software billing. Request quota increases through AWS Service Quotas if the account lacks enough EC2 instances, vCPUs, Elastic IPs, or EBS capacity. AWS infrastructure charges are billed separately by AWS.

**Support**

Email: support@corenovacloud.com
Web: https://www.corenovacloud.com/

Include AWS Region, AMI ID, EC2 Instance ID, instance type, and steps to reproduce."""


def latest_ami_delivery(version: dict[str, Any]) -> tuple[str, str]:
    sources = version.get("Sources") or []
    delivery_options = version.get("DeliveryOptions") or []
    if not sources:
        raise SystemExit("latest Marketplace version has no AMI source")
    if not delivery_options:
        raise SystemExit("latest Marketplace version has no delivery option")
    return sources[0]["Image"], delivery_options[0]["Id"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("product_key")
    parser.add_argument(
        "--remove-title-suffix",
        help="Remove this exact suffix from the submitted Marketplace product title.",
    )
    parser.add_argument(
        "--submitted-title",
        help="Use this exact Marketplace product title in the generated change set.",
    )
    parser.add_argument("--output-dir", default=str(ROOT / "plans"))
    args = parser.parse_args()

    product = product_by_key(args.product_key)
    details = assert_marketplace_product(product)["details"]
    version = latest_version(details)
    ami_id, delivery_option_id = latest_ami_delivery(version)
    if args.remove_title_suffix and product["title"].endswith(args.remove_title_suffix):
        product = dict(product)
        product["title"] = product["title"][: -len(args.remove_title_suffix)]
    if args.submitted_title:
        product = dict(product)
        product["title"] = args.submitted_title

    change_set = {
        "Catalog": product["_aws"]["marketplace_catalog"],
        "ChangeSet": [
            {
                "ChangeType": "UpdateInformation",
                "Entity": {
                    "Type": "AmiProduct@1.0",
                    "Identifier": product["entity_id"],
                },
                "DetailsDocument": {
                    "ProductTitle": product["title"],
                    "ShortDescription": short_description(product),
                    "LongDescription": long_description(product),
                    "Highlights": [
                        "Hardened EC2 AMI for production use with SSH key-only access, firewall baseline, auditd, AIDE, and automatic security updates.",
                        f"Architecture: {product['architecture']}; recommended instance type: {product['recommended_instance_type']}.",
                        "CIS-oriented OpenSCAP validation notes are included; not official CIS certification.",
                    ],
                    "SupportDescription": support_description(),
                },
            },
            {
                "ChangeType": "UpdateDeliveryOptions",
                "Entity": {
                    "Type": "AmiProduct@1.0",
                    "Identifier": product["entity_id"],
                },
                "DetailsDocument": {
                    "DeliveryOptions": [
                        {
                            "Id": delivery_option_id,
                            "Details": {
                                "AmiDeliveryOptionDetails": {
                                    "UsageInstructions": usage_instructions(product, ami_id),
                                    "RecommendedInstanceType": product[
                                        "recommended_instance_type"
                                    ],
                                }
                            },
                        }
                    ]
                },
            },
        ],
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{product['key']}-production-readiness.json"
    path.write_text(json.dumps(change_set, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
