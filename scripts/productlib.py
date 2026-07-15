#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS_FILE = ROOT / "products.yaml"
PRODUCTS_FILE_ENV = "CORENOVA_PRODUCTS_FILE"


def fail(message: str, code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def products_file() -> Path:
    configured = os.environ.get(PRODUCTS_FILE_ENV)
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            path = ROOT / path
        return path
    return PRODUCTS_FILE


def is_placeholder_entity(entity_id: str | None) -> bool:
    return not entity_id or entity_id in {"pending", "pending-create", "draft", "new"}


def load_config() -> dict[str, Any]:
    path = products_file()
    with path.open("r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    products = config.get("products") or []
    keys = [p["key"] for p in products]
    titles = [p["title"] for p in products]
    entities = [
        p.get("entity_id")
        for p in products
        if not is_placeholder_entity(p.get("entity_id"))
    ]
    for label, values in (("key", keys), ("title", titles), ("entity_id", entities)):
        if len(values) != len(set(values)):
            fail(f"duplicate product {label} in {path}")
    if path.resolve() == PRODUCTS_FILE.resolve() and len(products) != 11:
        fail(f"expected exactly 11 allowlisted products, found {len(products)}")
    return config


def product_by_key(product_key: str) -> dict[str, Any]:
    config = load_config()
    for product in config["products"]:
        if product["key"] == product_key:
            product = dict(product)
            product["_aws"] = config["aws"]
            return product
    allowed = ", ".join(p["key"] for p in config["products"])
    fail(f"product key {product_key!r} is not allowlisted. Allowed: {allowed}")


def product_instance_types(product: dict[str, Any]) -> list[str]:
    instance_types = product.get("instance_types")
    if instance_types:
        return list(instance_types)
    return [product["recommended_instance_type"]]


def run_aws(args: list[str], *, json_output: bool = True) -> Any:
    cmd = ["aws", *args]
    try:
        output = subprocess.check_output(cmd, text=True)
    except subprocess.CalledProcessError as exc:
        fail(f"AWS command failed: {' '.join(cmd)}\n{exc}")
    if json_output:
        return json.loads(output)
    return output.strip()


def assert_marketplace_product(product: dict[str, Any]) -> dict[str, Any]:
    entity = run_aws(
        [
            "marketplace-catalog",
            "describe-entity",
            "--catalog",
            product["_aws"]["marketplace_catalog"],
            "--entity-id",
            product["entity_id"],
            "--output",
            "json",
        ]
    )
    details = entity.get("DetailsDocument") or json.loads(entity["Details"])
    title = details.get("Description", {}).get("ProductTitle")
    if title != product["title"]:
        fail(
            "Marketplace entity/title mismatch for "
            f"{product['key']}: expected {product['title']!r}, got {title!r}"
        )
    return {"entity": entity, "details": details}


def latest_version(details: dict[str, Any]) -> dict[str, Any]:
    versions = details.get("Versions") or []
    if not versions:
        fail("Marketplace product has no versions")
    return versions[-1]


def version_title() -> str:
    from datetime import datetime, timezone

    return "v" + datetime.now(timezone.utc).strftime("%Y%m%d")


def usage_instructions(product: dict[str, Any], ami_id: str) -> str:
    if product.get("profile") == "eks-admin-bastion":
        return eks_admin_bastion_usage(product, ami_id)

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


def release_notes(product: dict[str, Any], ami_id: str, source_ami_id: str | None = None) -> str:
    if product.get("profile") == "eks-admin-bastion":
        source_line = f"\nSource AMI: {source_ami_id} (us-east-1)" if source_ami_id else ""
        return f"""{product["title"]}

Version: {version_title()}

Initial CoreNova EKS Admin Bastion release.

Baseline:
- Amazon Linux 2023 hardened base with current upstream security updates at build time.
- SSH key-only access, root login disabled, auditd, rsyslog, chrony, firewalld, and AIDE baseline.
- Amazon SSM Agent enabled for Session Manager access.
- EKS administration tools installed: AWS CLI v2, kubectl multi-version selector, Helm, eksctl, k9s, kubectx, kubens, jq, and yq.
- EKS helper scripts and starter IAM / Access Entry examples installed under /opt/corenova/eks; buyers must review and scope them.
- Cloud-init cleaned before image capture.
- Marketplace checks require unencrypted EBS snapshots and no existing product codes.

Architecture: {product["architecture"]}
Storage layout: {product["layout"]}
Filesystem: {product["filesystem"]}{source_line}
AMI: {ami_id} (us-east-1)

Security note: This AMI is designed for SSM-first administration. Keep inbound SSH closed unless your organization explicitly requires SSH fallback."""

    source_line = f"\nSource AMI: {source_ami_id} (us-east-1)" if source_ami_id else ""
    return f"""{product["title"]}

Version: {version_title()}

This release rebuilds the AMI with the standardized CoreNova builder-ami pipeline.

Baseline:
- Latest available upstream OS packages at build time.
- SSH key-only access, root login disabled.
- auditd, rsyslog, chrony, and AIDE baseline.
- Firewall baseline with SSH allowed.
- Automatic security update service enabled where supported.
- Cloud-init cleaned before image capture.
- Marketplace checks require unencrypted EBS snapshots and no existing product codes.

Architecture: {product["architecture"]}
Storage layout: {product["layout"]}
Filesystem: {product["filesystem"]}{source_line}
AMI: {ami_id} (us-east-1)

Compliance note: This image provides a hardened baseline and validation artifacts. Buyers should run their own compliance validation for their regulatory requirements."""


def eks_admin_bastion_usage(product: dict[str, Any], ami_id: str) -> str:
    return f"""**Overview**

{product["title"]} is an Amazon Linux 2023 EKS administration bastion AMI built by CoreNova Intelligence Limited.

Recommended instance type: {product["recommended_instance_type"]}.
AMI: {ami_id} (us-east-1).

**Recommended launch model**

1. Subscribe in AWS Marketplace, then launch in us-east-1.
2. Place the instance in a private subnet where it can reach AWS APIs.
3. Attach an IAM role with AmazonSSMManagedInstanceCore and EKS permissions that your team has reviewed and scoped.
4. Do not open inbound SSH to the internet. Use AWS Systems Manager Session Manager for shell access.
5. Review EC2 instance, EBS, data transfer, NAT gateway, VPC endpoint, and AWS Marketplace software charges before launch.

**First connection with Session Manager**

Install AWS CLI v2 and the Session Manager plugin on the operator workstation before connecting. The AMI includes and runs Amazon SSM Agent.

aws ssm start-session --target YOUR_INSTANCE_ID

**Optional SSH fallback**

The standalone Marketplace AMI launcher must display at least one security-group recommendation. CoreNova limits that recommendation to private RFC1918 sources. If you use Session Manager, remove the inbound TCP 22 rule after launch. If your organization requires SSH fallback, select an EC2 key pair and replace the recommendation with only your trusted administrator CIDRs.

ssh -i your-key.pem {product["ssh_username"]}@YOUR_PRIVATE_IP

**EKS setup**

aws eks update-kubeconfig --region YOUR_REGION --name YOUR_CLUSTER_NAME
kubectl get nodes
helm version
eksctl version
corenova-eks-check

**Installed tools**

- AWS CLI v2 and Amazon SSM Agent
- multiple kubectl clients with the kubectl-select helper; choose a version compatible with your cluster
- Helm, eksctl, k9s, kubectx, kubens
- jq, yq, git, tmux, and standard troubleshooting utilities

The included IAM discovery and EKS Access Entry examples are starting points. Review and scope them for your environment before use.

Examples and policy templates are installed under:

/opt/corenova/eks

**Post-launch local diagnostics**

systemctl is-active amazon-ssm-agent
systemctl is-active rsyslog
systemctl is-active chronyd
sudo sshd -T | grep -E 'permitrootlogin|passwordauthentication'
corenova-eks-check

Expected SSH settings:
permitrootlogin no
passwordauthentication no

**Sensitive data and credentials**

The AMI does not include hardcoded passwords, private keys, AWS credentials, kubeconfigs, or customer data. Customer-created keys, kubeconfigs, and Kubernetes secrets remain in the buyer's AWS account.

Anyone who can start a shell on this host can use its shared EC2 instance-role credentials and inherits that role's EKS permissions. Treat Session Manager access as a trusted-administrator boundary; the AMI does not provide per-user EKS identity isolation.

**Encryption**

The Marketplace source AMI uses unencrypted EBS snapshots as required for AWS Marketplace AMI ingestion. Buyers can launch or copy the AMI with encrypted EBS volumes according to their own AWS account policy.

**Service quotas and costs**

Before launch, check the regional EC2 On-Demand vCPU quota for the selected instance family and any Systems Manager or EKS quotas used by your deployment. Request increases through AWS Service Quotas when needed. EC2, EBS, networking, NAT gateway, VPC endpoint, data transfer, and AWS Marketplace software charges are billed separately.

**Support**

Email: support@corenovacloud.com
Web: https://www.corenovacloud.com/en/support/

Include AWS Region, AMI ID, EC2 Instance ID, instance type, EKS cluster version, tool output, and steps to reproduce."""
