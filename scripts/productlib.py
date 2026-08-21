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


def release_notes(
    product: dict[str, Any],
    ami_id: str,
    source_ami_id: str | None = None,
    release_version: str | None = None,
) -> str:
    effective_version = release_version or version_title()
    if product.get("profile") == "eks-admin-bastion":
        source_line = f"\nSource AMI: {source_ami_id} (us-east-1)" if source_ami_id else ""
        return f"""{product["title"]}

Version: {effective_version}

This release adds the Identity Relay and Audited Workstation deployment modes
while retaining the standalone AMI delivery option for compatibility.

Baseline:
- Amazon Linux 2023 hardened base with current upstream security updates at build time.
- SSH key-only access, root login disabled, auditd, rsyslog, chrony, firewalld, and AIDE baseline.
- Amazon SSM Agent enabled for Session Manager access.
- Non-root corenova-operator Run As account and read-only corenova-eks-doctor diagnostics.
- EKS administration tools installed: AWS CLI v2, kubectl multi-version selector, Helm, eksctl, k9s, kubectx, kubens, jq, and yq.
- EKS helper scripts and starter IAM / Access Entry examples installed under /opt/corenova/eks; buyers must review and scope them.
- Cloud-init cleaned before image capture.
- Marketplace checks require unencrypted EBS snapshots and no existing product codes.

Architecture: {product["architecture"]}
Storage layout: {product["layout"]}
Filesystem: {product["filesystem"]}{source_line}
AMI: {ami_id} (us-east-1)

Security note: Identity Relay keeps EKS authorization on each operator identity.
Audited Workstation streams standard shell sessions to CloudWatch Logs but uses
a shared EC2 role. Session Manager cannot log port-forwarded session contents.
Keep inbound SSH closed unless your organization explicitly requires fallback."""

    source_line = f"\nSource AMI: {source_ami_id} (us-east-1)" if source_ami_id else ""
    return f"""{product["title"]}

Version: {effective_version}

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

For versions that display CloudFormation delivery options in AWS Marketplace,
choose Identity Relay for per-user EKS authorization or Audited Workstation for
a streamed administrative shell. AWS Marketplace opens CloudFormation directly.

For the standalone AMI compatibility path:

1. Subscribe in AWS Marketplace, then launch in the supported Region.
2. Place the instance in a private subnet where it can reach AWS APIs.
3. Attach AmazonSSMManagedInstanceCore and only reviewed, scoped EKS permissions.
4. Keep inbound SSH closed and use AWS Systems Manager Session Manager.
5. Review AWS infrastructure, logging, networking, and software charges.

**First connection with Session Manager**

Install AWS CLI v2 and the Session Manager plugin on the operator workstation.

aws ssm start-session --target YOUR_INSTANCE_ID

**Optional SSH fallback**

The standalone launcher requires a security-group recommendation, limited here
to private RFC1918 sources. Remove inbound TCP 22 when using Session Manager. If
SSH fallback is required, select a key pair and allow only trusted admin CIDRs.

ssh -i your-key.pem {product["ssh_username"]}@YOUR_PRIVATE_IP

**EKS setup**

aws eks update-kubeconfig --region YOUR_REGION --name YOUR_CLUSTER_NAME
kubectl auth can-i get pods --namespace YOUR_NAMESPACE
kubectl get pods --namespace YOUR_NAMESPACE
corenova-eks-check
corenova-eks-doctor --cluster YOUR_CLUSTER_NAME --region YOUR_REGION

**Installed tools**

AWS CLI v2, SSM Agent, multiple kubectl clients, Helm, eksctl, k9s, kubectx,
kubens, jq, yq, git, tmux, and troubleshooting utilities are included. Review
and scope the IAM and EKS Access Entry examples under /opt/corenova/eks.

**Post-launch local diagnostics**

systemctl is-active amazon-ssm-agent
systemctl is-active rsyslog
systemctl is-active chronyd
sudo sshd -T | grep -E 'permitrootlogin|passwordauthentication'
corenova-eks-check

Expected SSH settings are permitrootlogin no and passwordauthentication no.

**Security boundaries**

The AMI has no hardcoded passwords, private keys, AWS credentials, kubeconfigs,
or customer data. Buyer-created credentials and data remain in the buyer account.

Anyone who can start a shell on this host can use its shared EC2 instance-role credentials and inherits that role's EKS permissions. Treat Session Manager access as a trusted-administrator boundary; the AMI does not provide per-user EKS identity isolation.

Identity Relay instead keeps EKS permissions on the operator identity. Session
Manager cannot record port-forwarded content; use Audited Workstation when
recorded shell commands are required.

**Encryption**

The Marketplace source uses unencrypted snapshots for ingestion. Buyers can
launch or copy it with encrypted EBS volumes under their account policy.

**Service quotas and costs**

Check regional EC2, Systems Manager, and EKS quotas before launch. EC2, EBS,
networking, logging, data transfer, and Marketplace software are billed separately.

**Support**

Email: support@corenovacloud.com
Web: https://www.corenovacloud.com/en/support/

Include Region, AMI and Instance IDs, instance type, EKS version, command output,
and reproduction steps."""
