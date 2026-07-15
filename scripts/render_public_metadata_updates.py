#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CATALOG = "AWSMarketplace"
SELLER_PROFILE_URL = "https://aws.amazon.com/marketplace/seller-profile?id=seller-kbf3ztbtbdc5o"
CORENOVA_URL = "https://www.corenovacloud.com/"

RELATED_URLS = {
    "ubuntu_2204": "https://aws.amazon.com/marketplace/pp/prodview-u66ma5qrdkvtw",
    "amazon_linux_2023": "https://aws.amazon.com/marketplace/pp/prodview-gricbzzlztsae",
    "ai_sandbox": "https://aws.amazon.com/marketplace/pp/prodview-os7kg3e24oqpw",
    "gpu_cuda": "https://aws.amazon.com/marketplace/pp/prodview-s3rsuk6sunlwq",
}

LISTING_URLS: dict[str, dict[str, str]] = {}

RELATED_ENTITY_IDS = {
    "prod-4tnfzjf4ynkgw": [
        "prod-7cvvy2gp6ryoc",
        "prod-hqk6nphpcucgk",
        "prod-fltwx2ns5fmss",
    ],
    "prod-7cvvy2gp6ryoc": [
        "prod-hqk6nphpcucgk",
        "prod-4tnfzjf4ynkgw",
        "prod-fltwx2ns5fmss",
    ],
    "prod-hqk6nphpcucgk": [
        "prod-7cvvy2gp6ryoc",
        "prod-4tnfzjf4ynkgw",
        "prod-fltwx2ns5fmss",
    ],
    "prod-fltwx2ns5fmss": [
        "prod-sigm7ovzlqdte",
        "prod-hqk6nphpcucgk",
        "prod-7cvvy2gp6ryoc",
    ],
    "prod-sigm7ovzlqdte": [
        "prod-fltwx2ns5fmss",
        "prod-hqk6nphpcucgk",
        "prod-c2q4h76hz3u4k",
    ],
    "prod-jxjqud52zrofw": [
        "prod-fkmhgwyoiz5ls",
        "prod-c2q4h76hz3u4k",
        "prod-r2ldqznatcigs",
    ],
    "prod-fkmhgwyoiz5ls": [
        "prod-jxjqud52zrofw",
        "prod-7cvvy2gp6ryoc",
        "prod-c2q4h76hz3u4k",
    ],
    "prod-lyolayhuy6hi2": [
        "prod-j4fhcdjn5o46o",
        "prod-uca3f3ujrl5gg",
        "prod-nptqkfuwrh5ik",
    ],
    "prod-j4fhcdjn5o46o": [
        "prod-lyolayhuy6hi2",
        "prod-uca3f3ujrl5gg",
        "prod-fkmhgwyoiz5ls",
    ],
    "prod-ereepz5xafyw2": [
        "prod-uca3f3ujrl5gg",
        "prod-lyolayhuy6hi2",
        "prod-nptqkfuwrh5ik",
    ],
    "prod-uca3f3ujrl5gg": [
        "prod-j4fhcdjn5o46o",
        "prod-fkmhgwyoiz5ls",
        "prod-lyolayhuy6hi2",
    ],
    "prod-nptqkfuwrh5ik": [
        "prod-lyolayhuy6hi2",
        "prod-uca3f3ujrl5gg",
        "prod-jxjqud52zrofw",
    ],
    "prod-hv5ebdtqf2too": [
        "prod-7cvvy2gp6ryoc",
        "prod-4tnfzjf4ynkgw",
        "prod-fkmhgwyoiz5ls",
    ],
    "prod-c2q4h76hz3u4k": [
        "prod-r2ldqznatcigs",
        "prod-jxjqud52zrofw",
        "prod-sigm7ovzlqdte",
    ],
    "prod-r2ldqznatcigs": [
        "prod-c2q4h76hz3u4k",
        "prod-jxjqud52zrofw",
        "prod-fkmhgwyoiz5ls",
    ],
}


@dataclass(frozen=True)
class ProductPlan:
    entity_id: str
    group: str
    os_display: str
    architecture: str
    storage: str
    default_user: str
    recommended_instance: str
    keywords: list[str]
    related: list[tuple[str, str]]
    charge_kind: str = "open source software"


PLANS: dict[str, ProductPlan] = {
    "prod-ereepz5xafyw2": ProductPlan(
        "prod-ereepz5xafyw2",
        "linux",
        "AlmaLinux 9",
        "x86_64",
        "LVM with XFS for separated operating-system paths and online growth.",
        "ec2-user",
        "t3.medium",
        ["secure linux ami", "cis baseline", "lvm xfs"],
        [
            ("Amazon Linux 2023 Hardened AMI", RELATED_URLS["amazon_linux_2023"]),
            ("Ubuntu 22.04 LTS Hardened AMI", RELATED_URLS["ubuntu_2204"]),
        ],
    ),
    "prod-lyolayhuy6hi2": ProductPlan(
        "prod-lyolayhuy6hi2",
        "linux",
        "Rocky Linux 9",
        "x86_64",
        "LVM with XFS for separated operating-system paths and online growth.",
        "rocky",
        "t3.medium",
        ["secure linux ami", "cis baseline", "lvm xfs"],
        [
            ("Amazon Linux 2023 Hardened AMI", RELATED_URLS["amazon_linux_2023"]),
            ("Ubuntu 22.04 LTS Hardened AMI", RELATED_URLS["ubuntu_2204"]),
        ],
    ),
    "prod-7cvvy2gp6ryoc": ProductPlan(
        "prod-7cvvy2gp6ryoc",
        "linux",
        "Ubuntu 22.04 LTS",
        "arm64",
        "LVM with XFS for separated operating-system paths and online growth.",
        "ubuntu",
        "t4g.medium",
        ["graviton hardened", "arm64 cis baseline", "lvm xfs"],
        [
            ("Ubuntu 22.04 LTS Hardened AMI", RELATED_URLS["ubuntu_2204"]),
            ("GPU CUDA Ubuntu Hardened AMI", RELATED_URLS["gpu_cuda"]),
        ],
    ),
    "prod-uca3f3ujrl5gg": ProductPlan(
        "prod-uca3f3ujrl5gg",
        "linux",
        "AlmaLinux 9",
        "arm64",
        "LVM with XFS for separated operating-system paths and online growth.",
        "ec2-user",
        "t4g.medium",
        ["graviton hardened", "arm64 cis baseline", "lvm xfs"],
        [
            ("Amazon Linux 2023 Graviton Hardened", RELATED_URLS["amazon_linux_2023"]),
            ("Ubuntu 22.04 LTS Hardened AMI", RELATED_URLS["ubuntu_2204"]),
        ],
    ),
    "prod-4tnfzjf4ynkgw": ProductPlan(
        "prod-4tnfzjf4ynkgw",
        "linux",
        "Ubuntu 24.04 LTS",
        "arm64",
        "LVM with XFS for separated operating-system paths and online growth.",
        "ubuntu",
        "t4g.medium",
        ["graviton hardened", "arm64 cis baseline", "lvm xfs"],
        [
            ("Ubuntu 22.04 LTS Hardened AMI", RELATED_URLS["ubuntu_2204"]),
            ("GPU CUDA Ubuntu Hardened AMI", RELATED_URLS["gpu_cuda"]),
        ],
    ),
    "prod-hv5ebdtqf2too": ProductPlan(
        "prod-hv5ebdtqf2too",
        "linux",
        "Debian 12 Bookworm",
        "arm64",
        "LVM-backed layout for operating-system and workload data.",
        "admin",
        "t4g.medium",
        ["graviton hardened", "arm64 cis baseline", "debian server"],
        [
            ("Ubuntu 22.04 LTS Hardened AMI", RELATED_URLS["ubuntu_2204"]),
            ("Amazon Linux 2023 Hardened AMI", RELATED_URLS["amazon_linux_2023"]),
        ],
    ),
    "prod-j4fhcdjn5o46o": ProductPlan(
        "prod-j4fhcdjn5o46o",
        "linux",
        "Rocky Linux 9",
        "arm64",
        "LVM with XFS for separated operating-system paths and online growth.",
        "rocky",
        "t4g.medium",
        ["graviton hardened", "arm64 cis baseline", "lvm xfs"],
        [
            ("Amazon Linux 2023 Graviton Hardened", RELATED_URLS["amazon_linux_2023"]),
            ("Ubuntu 22.04 LTS Hardened AMI", RELATED_URLS["ubuntu_2204"]),
        ],
    ),
    "prod-nptqkfuwrh5ik": ProductPlan(
        "prod-nptqkfuwrh5ik",
        "linux",
        "CentOS Stream 9",
        "x86_64",
        "Standard Ext4 root volume.",
        "ec2-user",
        "t3.medium",
        ["hardened base image", "cis baseline", "centos stream"],
        [
            ("Amazon Linux 2023 Hardened AMI", RELATED_URLS["amazon_linux_2023"]),
            ("Ubuntu 22.04 LTS Hardened AMI", RELATED_URLS["ubuntu_2204"]),
        ],
    ),
    "prod-hqk6nphpcucgk": ProductPlan(
        "prod-hqk6nphpcucgk",
        "linux",
        "Ubuntu 22.04 LTS",
        "x86_64",
        "Standard Ext4 root volume.",
        "ubuntu",
        "t3.medium",
        ["secure linux ami", "cis baseline", "ubuntu server"],
        [
            ("Amazon Linux 2023 Hardened AMI", RELATED_URLS["amazon_linux_2023"]),
            ("GPU CUDA Ubuntu Hardened AMI", RELATED_URLS["gpu_cuda"]),
        ],
    ),
    "prod-fkmhgwyoiz5ls": ProductPlan(
        "prod-fkmhgwyoiz5ls",
        "linux",
        "Amazon Linux 2023",
        "arm64",
        "Ext4 root volume with Amazon Linux 2023 ARM64 64K-page kernel support.",
        "ec2-user",
        "t4g.medium",
        ["graviton hardened", "64k page linux", "cis baseline"],
        [
            ("Amazon Linux 2023 Hardened AMI", RELATED_URLS["amazon_linux_2023"]),
            ("Ubuntu 22.04 LTS Hardened AMI", RELATED_URLS["ubuntu_2204"]),
        ],
        charge_kind="software",
    ),
    "prod-jxjqud52zrofw": ProductPlan(
        "prod-jxjqud52zrofw",
        "linux",
        "Amazon Linux 2023",
        "x86_64",
        "Standard Ext4 root volume.",
        "ec2-user",
        "t3.medium",
        ["secure linux ami", "cis baseline", "amazon linux"],
        [
            ("Ubuntu 22.04 LTS Hardened AMI", RELATED_URLS["ubuntu_2204"]),
            ("Amazon Linux 2023 Graviton Hardened", RELATED_URLS["amazon_linux_2023"]),
        ],
        charge_kind="software",
    ),
    "prod-sigm7ovzlqdte": ProductPlan(
        "prod-sigm7ovzlqdte",
        "ai",
        "Ubuntu 22.04 LTS",
        "x86_64 GPU",
        "Root volume plus optional secondary gp3 model volume mounted at /mnt/models.",
        "ubuntu",
        "g5.xlarge",
        ["private llm", "local inference", "open webui"],
        [
            ("GPU CUDA Ubuntu Hardened AMI", RELATED_URLS["gpu_cuda"]),
            ("Ubuntu 22.04 LTS Hardened AMI", RELATED_URLS["ubuntu_2204"]),
        ],
    ),
    "prod-fltwx2ns5fmss": ProductPlan(
        "prod-fltwx2ns5fmss",
        "gpu",
        "Ubuntu 22.04 LTS",
        "x86_64 GPU",
        "Standard root volume for GPU compute workloads.",
        "ubuntu",
        "g5.xlarge",
        ["cuda ami", "gpu compute", "hardened ubuntu"],
        [
            ("Private AI Sandbox AMI", RELATED_URLS["ai_sandbox"]),
            ("Ubuntu 22.04 LTS Hardened AMI", RELATED_URLS["ubuntu_2204"]),
        ],
    ),
    "prod-r2ldqznatcigs": ProductPlan(
        "prod-r2ldqznatcigs",
        "cloud_forge_db",
        "Amazon Linux 2023",
        "x86_64",
        "Runtime disk for Docker-based database and stateful workloads.",
        "ec2-user",
        "t3.medium",
        ["self-hosted databases", "database ami", "cloudformation deploy"],
        [
            ("Cloud Forge Hardened App Runtime", CORENOVA_URL),
            ("Amazon Linux 2023 Hardened AMI", RELATED_URLS["amazon_linux_2023"]),
        ],
        charge_kind="software",
    ),
    "prod-c2q4h76hz3u4k": ProductPlan(
        "prod-c2q4h76hz3u4k",
        "cloud_forge_app",
        "Amazon Linux 2023",
        "x86_64",
        "Runtime disk for Docker Compose application stacks.",
        "ec2-user",
        "t3.medium",
        ["self-hosted apps", "docker runtime", "cloudformation deploy"],
        [
            ("Cloud Forge Hardened Database AMI", CORENOVA_URL),
            ("Amazon Linux 2023 Hardened AMI", RELATED_URLS["amazon_linux_2023"]),
        ],
        charge_kind="software",
    ),
}


def aws_json(args: list[str]) -> dict[str, Any]:
    out = subprocess.check_output(args, text=True)
    return json.loads(out)


def list_public_ami_products() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    token = None
    while True:
        cmd = [
            "aws",
            "marketplace-catalog",
            "list-entities",
            "--catalog",
            CATALOG,
            "--entity-type",
            "AmiProduct",
            "--max-results",
            "50",
            "--output",
            "json",
        ]
        if token:
            cmd.extend(["--next-token", token])
        data = aws_json(cmd)
        rows.extend(
            row
            for row in data.get("EntitySummaryList", [])
            if row.get("Visibility") == "Public"
        )
        token = data.get("NextToken")
        if not token:
            return rows


def discover_listing_urls() -> dict[str, dict[str, str]]:
    data = aws_json(
        [
            "aws",
            "marketplace-discovery",
            "search-listings",
            "--filters",
            "filterType=PUBLISHER,filterValues=seller-kbf3ztbtbdc5o",
            "--region",
            "us-east-1",
            "--output",
            "json",
            "--max-items",
            "50",
        ]
    )
    mapping: dict[str, dict[str, str]] = {}
    for listing in data.get("listingSummaries", []):
        product = ((listing.get("associatedEntities") or [{}])[0]).get("product") or {}
        product_id = product.get("productId")
        listing_id = listing.get("listingId")
        if product_id and listing_id:
            mapping[product_id] = {
                "listing_id": listing_id,
                "name": listing.get("listingName") or product.get("productName") or product_id,
                "url": f"https://aws.amazon.com/marketplace/pp/{listing_id}",
            }
    return mapping


def describe_entity(entity_id: str) -> dict[str, Any]:
    return aws_json(
        [
            "aws",
            "marketplace-catalog",
            "describe-entity",
            "--catalog",
            CATALOG,
            "--entity-id",
            entity_id,
            "--output",
            "json",
        ]
    )


def details_document(entity: dict[str, Any]) -> dict[str, Any]:
    return entity.get("DetailsDocument") or json.loads(entity["Details"])


def resource_links() -> list[dict[str, str]]:
    return [
        {"Text": "CoreNova support", "Url": CORENOVA_URL},
        {"Text": "CoreNova AWS Marketplace catalog", "Url": SELLER_PROFILE_URL},
    ]


def related_section(plan: ProductPlan) -> str:
    lines = []
    for entity_id in RELATED_ENTITY_IDS.get(plan.entity_id, []):
        listing = LISTING_URLS.get(entity_id)
        if not listing:
            continue
        lines.append(f"- {listing['name']}: {listing['url']}")
    lines.append(f"- Full CoreNova catalog: {SELLER_PROFILE_URL}")
    return "\n".join(lines)


def charge_opening(plan: ProductPlan) -> str:
    return (
        f"This is a repackaged {plan.charge_kind} product wherein additional charges "
        "apply for CoreNova hardening, maintenance, validation notes, and seller support."
    )


def short_linux(title: str, plan: ProductPlan) -> str:
    return (
        "This product has charges associated with it for CoreNova hardening, "
        f"maintenance, validation notes, and seller support. {title} provides "
        f"a hardened {plan.os_display} EC2 baseline with SSH lockdown, audit logging, "
        "AIDE, firewall controls, and buyer-side OpenSCAP notes."
    )


def long_linux(title: str, plan: ProductPlan) -> str:
    extra = []
    if "LVM" in plan.storage or "LVM" in title:
        extra.append("- Online volume-growth helper for LVM-based layouts.")
    if "64K" in title or "64K-page" in plan.storage:
        extra.append("- ARM64 64K-page kernel support for compatible Graviton workloads.")
    if plan.os_display.startswith("Amazon Linux"):
        extra.append("- SELinux-oriented Amazon Linux 2023 baseline where supported.")
    extra_block = "\n".join(extra)
    if extra_block:
        extra_block = "\n" + extra_block

    return f"""{charge_opening(plan)}

{title} is a hardened EC2 AMI for teams that need a repeatable {plan.os_display} baseline on AWS. It is designed for platform engineering, DevOps, and security teams that want faster launch paths without building every host-control baseline from scratch.

**Included baseline**

- SSH key-only access with root login disabled; default user: {plan.default_user}.
- Host firewall baseline with administrator SSH access.
- auditd, rsyslog, chrony, and AIDE configured during image build.
- Automatic security updates enabled where supported by the operating system.
- OpenSCAP and CIS-oriented validation notes for buyer-side review.{extra_block}

**Best for**

- Bastion hosts and jump boxes with key-only administration.
- Application servers that need a documented hardened OS baseline.
- Security-sensitive labs, demos, and production-oriented EC2 workloads.
- Teams standardizing on {plan.os_display} across AWS accounts.

**Storage and architecture**

{plan.storage}

Architecture: {plan.architecture}.
Recommended instance type: {plan.recommended_instance}.

**Security and compliance**

This listing provides a hardened baseline and documentation intended to help buyers validate controls in their own AWS accounts. It is not an official CIS-certified image. Buyers remain responsible for organization-specific compliance validation, patch policy, logging retention, and workload configuration.

**Related CoreNova listings**

{related_section(plan)}

**Support**

Email: support@corenovacloud.com
Web: {CORENOVA_URL}

Include AWS Region, AMI ID, EC2 Instance ID, instance type, and steps to reproduce when opening a support request."""


def short_ai(title: str, plan: ProductPlan) -> str:
    return (
        "This product has charges associated with it for CoreNova hardening, AI stack "
        f"packaging, maintenance, and seller support. {title} packages Open WebUI, "
        "Ollama, vLLM, CUDA tooling, and HTTPS access for private LLM inference in "
        "your AWS account."
    )


def long_ai(title: str, plan: ProductPlan) -> str:
    return f"""{charge_opening(plan)}

{title} is a private AI sandbox AMI for running local LLM workflows inside your AWS account. It packages a hardened Ubuntu base with Open WebUI, Ollama, vLLM, Docker, NVIDIA runtime integration, and an HTTPS front end so teams can launch an isolated AI workspace faster.

**Included AI stack**

- Open WebUI for browser-based chat, RAG workflows, and administration.
- Ollama for local GGUF model serving; models are bring-your-own-model and are not bundled.
- vLLM as an optional high-throughput OpenAI-compatible inference server.
- Docker and NVIDIA container runtime integration for GPU instances.
- HTTPS access through Nginx, with self-signed TLS on first boot that buyers can replace with their own certificate.

**First access**

After launch, allow 5 to 10 minutes for initialization. Open https://YOUR_PUBLIC_IP/ and sign in with the seeded administrator account. Public signup is disabled by default. Change the administrator password after first login.

**Security and privacy**

- Prompts, uploaded documents, embeddings, and model files remain in the buyer's AWS account.
- Ollama and vLLM bind locally by default rather than exposing inference APIs directly to the internet.
- SSH hardening, firewall controls, fail2ban, auditd, and unattended security updates are included where supported.
- Optional secondary gp3 storage can be mounted at /mnt/models for model weights.

**Best for**

- Private AI demos and proof-of-concept deployments.
- Teams testing local inference before building a larger platform.
- Internal chat and RAG experiments where data should stay inside a VPC.

**Related CoreNova listings**

{related_section(plan)}

**Support**

Email: support@corenovacloud.com
Web: {CORENOVA_URL}

Include AWS Region, AMI ID, EC2 Instance ID, GPU instance type, browser error details, and steps to reproduce when opening a support request."""


def short_gpu(title: str, plan: ProductPlan) -> str:
    return (
        "This product has charges associated with it for CoreNova hardening, CUDA "
        f"packaging, maintenance, and seller support. {title} includes NVIDIA driver, "
        "CUDA tooling, and a security baseline for EC2 GPU compute workloads."
    )


def long_gpu(title: str, plan: ProductPlan) -> str:
    return f"""{charge_opening(plan)}

{title} is a hardened Ubuntu GPU AMI for EC2 machine learning, CUDA development, and GPU compute workloads. It is designed for buyers who want a ready CUDA host baseline without manually installing NVIDIA drivers, CUDA tooling, and operating-system hardening on every instance.

**Included baseline**

- Ubuntu 22.04 LTS with NVIDIA GPU driver and CUDA tooling.
- SSH key-only access with root login disabled.
- UFW firewall baseline, auditd, AIDE, rsyslog, and automatic security updates where supported.
- GPU readiness checks such as nvidia-smi and CUDA compiler validation.
- CIS-oriented OpenSCAP notes for buyer-side validation; not official CIS certification.

**Best for**

- GPU development hosts on G4dn, G5, and P-family EC2 instances.
- ML experiment environments that need CUDA-ready launch behavior.
- Teams that want a hardened Ubuntu base before installing ML frameworks.

**Security and operations**

The image does not include customer data, private keys, or model weights. Buyers should restrict SSH to trusted administrator networks, review GPU and storage costs before launch, and apply their own workload-level access controls.

**Related CoreNova listings**

{related_section(plan)}

**Support**

Email: support@corenovacloud.com
Web: {CORENOVA_URL}

Include AWS Region, AMI ID, EC2 Instance ID, GPU instance type, NVIDIA/CUDA command output, and steps to reproduce when opening a support request."""


def short_cloud_forge(title: str, plan: ProductPlan) -> str:
    if plan.group == "cloud_forge_db":
        purpose = "database and stateful workload deployments"
    else:
        purpose = "self-hosted app deployments"
    return (
        "This product has charges associated with it for Cloud Forge runtime "
        f"hardening, automation, maintenance, and seller support. {title} provides "
        f"a Docker and CloudFormation-ready Amazon Linux runtime for {purpose}."
    )


def long_cloud_forge(title: str, plan: ProductPlan) -> str:
    if plan.group == "cloud_forge_db":
        included = [
            "Docker and Docker Compose for database containers.",
            "Bootstrap automation for Cloud Forge database catalog entries.",
            "Database-oriented host tuning and native TCP access patterns.",
            "AWS Systems Manager Agent support for administration.",
        ]
        best_for = [
            "Self-hosted databases from the Cloud Forge catalog.",
            "Stateful single-node data services on EC2.",
            "Repeatable CloudFormation-backed database deployments.",
        ]
    else:
        included = [
            "Docker, Docker Compose, and Caddy reverse proxy.",
            "Bootstrap automation for Cloud Forge app catalog entries.",
            "HTTP fallback, domain HTTPS, and internal TLS modes.",
            "AWS Systems Manager Agent support for administration.",
        ]
        best_for = [
            "Self-hosted open-source applications from the Cloud Forge catalog.",
            "Caddy-fronted Docker Compose application stacks.",
            "Repeatable CloudFormation-backed app deployments.",
        ]

    included_block = "\n".join(f"- {line}" for line in included)
    best_for_block = "\n".join(f"- {line}" for line in best_for)

    return f"""{charge_opening(plan)}

{title} is an Amazon Linux 2023 runtime AMI for Cloud Forge deployments. It is designed to give small teams a repeatable EC2 host layer for launching self-hosted software through CloudFormation-driven workflows.

**Included runtime**

{included_block}
- Basic host hardening and cleanup during AMI build.
- Runtime capability metadata under /etc/cloud-forge where applicable.

**Best for**

{best_for_block}
- Testing Cloud Forge templates before promoting them to production.

**Security and operations**

This AMI has an AWS Marketplace software fee. AWS infrastructure costs such as EC2, EBS, public IPv4, Elastic IP, and data transfer are billed separately by AWS. Buyers should restrict SSH and service ports to trusted networks and keep application credentials in their own AWS account.

**Related CoreNova listings**

{related_section(plan)}

**Support**

Email: support@corenovacloud.com
Web: {CORENOVA_URL}

Include AWS Region, AMI ID, EC2 Instance ID, CloudFormation stack name, instance type, and steps to reproduce when opening a support request."""


def build_copy(title: str, plan: ProductPlan) -> tuple[str, str, list[str]]:
    if plan.group == "ai":
        return (
            short_ai(title, plan),
            long_ai(title, plan),
            [
                "Private AI sandbox with Open WebUI, Ollama, vLLM, CUDA runtime integration, and HTTPS access.",
                "Designed for local LLM inference inside the buyer's AWS account with signup disabled by default.",
                "Hardened Ubuntu baseline with firewall controls, audit logging, fail2ban, and seller support.",
            ],
        )
    if plan.group == "gpu":
        return (
            short_gpu(title, plan),
            long_gpu(title, plan),
            [
                "Ubuntu GPU AMI with NVIDIA driver and CUDA tooling ready for EC2 GPU workloads.",
                "Includes SSH lockdown, firewall baseline, auditd, AIDE, and automatic security updates where supported.",
                "Suitable for ML development, GPU compute, and CUDA validation on supported GPU instances.",
            ],
        )
    if plan.group.startswith("cloud_forge"):
        return (
            short_cloud_forge(title, plan),
            long_cloud_forge(title, plan),
            [
                "Amazon Linux 2023 runtime hardened for Cloud Forge CLI and CloudFormation deployments.",
                "Includes Docker automation, SSM support, bootstrap services, and host security controls.",
                "Built for repeatable self-hosted app or database deployments in the buyer's AWS account.",
            ],
        )
    return (
        short_linux(title, plan),
        long_linux(title, plan),
        [
            "Hardened EC2 AMI with SSH key-only access, firewall baseline, auditd, AIDE, and automatic security updates where supported.",
            f"Architecture: {plan.architecture}; recommended instance type: {plan.recommended_instance}.",
            "CIS-oriented OpenSCAP validation notes are included for buyer-side review; not official CIS certification.",
        ],
    )


def support_description() -> str:
    return f"""Email: support@corenovacloud.com

Web: {CORENOVA_URL}

CoreNova supports launch, SSH access, baseline service checks, Marketplace AMI metadata, and documented hardening behavior. Include AWS Region, AMI ID, EC2 Instance ID, instance type, and steps to reproduce.

Refund: 30-day refund on Marketplace software fees for verified technical issues. AWS infrastructure charges are billed by AWS and are not refundable by the seller."""


def render_change_set(entity: dict[str, Any]) -> dict[str, Any]:
    entity_id = entity["EntityId"]
    plan = PLANS[entity_id]
    described = describe_entity(entity_id)
    details = details_document(described)
    description = details["Description"]
    title = description["ProductTitle"]
    short, long, highlights = build_copy(title, plan)
    return {
        "Catalog": CATALOG,
        "ChangeSet": [
            {
                "ChangeType": "UpdateInformation",
                "Entity": {"Type": "AmiProduct@1.0", "Identifier": entity_id},
                "DetailsDocument": {
                    "ProductTitle": title,
                    "ShortDescription": short,
                    "LongDescription": long,
                    "Highlights": highlights,
                    "SearchKeywords": plan.keywords,
                    "AdditionalResources": resource_links(),
                    "SupportDescription": support_description(),
                },
            }
        ],
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    global LISTING_URLS
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "plans" / "public-metadata"))
    parser.add_argument("--backup-dir", default=str(ROOT / "backups" / "marketplace-public-metadata"))
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_dir) / stamp
    backup_dir = Path(args.backup_dir) / stamp

    public = list_public_ami_products()
    LISTING_URLS = discover_listing_urls()
    unknown = sorted({row["EntityId"] for row in public} - set(PLANS))
    if unknown:
        raise SystemExit(f"missing ProductPlan for public AMI products: {', '.join(unknown)}")

    summary = []
    for entity in public:
        described = describe_entity(entity["EntityId"])
        details = details_document(described)
        write_json(backup_dir / f"{entity['EntityId']}.json", described)
        change_set = render_change_set(entity)
        title = details["Description"]["ProductTitle"]
        path = output_dir / f"{entity['EntityId']}-update-information.json"
        write_json(path, change_set)
        summary.append(
            {
                "entity_id": entity["EntityId"],
                "title": title,
                "plan": str(path),
                "backup": str(backup_dir / f"{entity['EntityId']}.json"),
                "keywords": change_set["ChangeSet"][0]["DetailsDocument"]["SearchKeywords"],
                "short_len": len(
                    change_set["ChangeSet"][0]["DetailsDocument"]["ShortDescription"]
                ),
                "long_len": len(
                    change_set["ChangeSet"][0]["DetailsDocument"]["LongDescription"]
                ),
            }
        )

    write_json(output_dir / "summary.json", summary)
    print(output_dir)


if __name__ == "__main__":
    main()
