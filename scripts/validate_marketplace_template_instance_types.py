#!/usr/bin/env python3
"""Match Marketplace CloudFormation instance types to live product support."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any
from urllib.request import Request, urlopen

import yaml


class CloudFormationLoader(yaml.SafeLoader):
    pass


def construct_intrinsic(
    loader: CloudFormationLoader, tag_suffix: str, node: yaml.Node
) -> dict[str, Any]:
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
    else:
        value = loader.construct_mapping(node)
    return {tag_suffix: value}


CloudFormationLoader.add_multi_constructor("!", construct_intrinsic)


def load_template_text(text: str, label: str) -> dict[str, Any]:
    value = yaml.load(text, Loader=CloudFormationLoader)
    if not isinstance(value, dict):
        raise ValueError(f"{label}: expected a CloudFormation mapping")
    return value


def instance_type_candidates(template: dict[str, Any], label: str) -> set[str]:
    resources = template.get("Resources")
    parameters = template.get("Parameters")
    if not isinstance(resources, dict) or not isinstance(parameters, dict):
        raise ValueError(f"{label}: missing Resources or Parameters")

    candidates: set[str] = set()
    instance_count = 0
    for logical_id, resource in resources.items():
        if not isinstance(resource, dict) or resource.get("Type") != "AWS::EC2::Instance":
            continue
        instance_count += 1
        properties = resource.get("Properties")
        if not isinstance(properties, dict):
            raise ValueError(f"{label}: {logical_id} has no Properties mapping")
        instance_type = properties.get("InstanceType")
        if isinstance(instance_type, str):
            candidates.add(instance_type)
            continue
        if not isinstance(instance_type, dict) or set(instance_type) != {"Ref"}:
            raise ValueError(
                f"{label}: {logical_id} InstanceType must be a literal or Ref"
            )
        parameter_name = instance_type["Ref"]
        parameter = parameters.get(parameter_name)
        if not isinstance(parameter, dict):
            raise ValueError(
                f"{label}: {logical_id} references missing parameter {parameter_name}"
            )
        allowed = parameter.get("AllowedValues")
        if not isinstance(allowed, list) or not allowed or not all(
            isinstance(value, str) and value for value in allowed
        ):
            raise ValueError(
                f"{label}: {parameter_name} needs explicit non-empty AllowedValues"
            )
        default = parameter.get("Default")
        if default not in allowed:
            raise ValueError(
                f"{label}: {parameter_name} default must be in AllowedValues"
            )
        candidates.update(allowed)
    if instance_count == 0:
        raise ValueError(f"{label}: no AWS::EC2::Instance resource found")
    return candidates


def validate_template_instance_types(
    template: dict[str, Any], supported: set[str], label: str
) -> set[str]:
    if not supported:
        raise ValueError(f"{label}: live product has no supported instance types")
    candidates = instance_type_candidates(template, label)
    unsupported = sorted(candidates - supported)
    if unsupported:
        raise ValueError(
            f"{label}: unsupported Marketplace product instance types: {unsupported}"
        )
    return candidates


def live_product_instance_types(product_id: str, region: str) -> set[str]:
    result = subprocess.run(
        [
            "aws",
            "marketplace-catalog",
            "describe-entity",
            "--region",
            region,
            "--catalog",
            "AWSMarketplace",
            "--entity-id",
            product_id,
            "--output",
            "json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    entity = json.loads(result.stdout)
    details = json.loads(entity["Details"])
    available = (details.get("Compatibility") or {}).get("AvailableInstanceTypes")
    if not isinstance(available, list) or not all(
        isinstance(value, str) and value for value in available
    ):
        raise ValueError(
            f"{product_id}: live entity has no valid AvailableInstanceTypes"
        )
    return set(available)


def download_template(url: str) -> str:
    if not url.startswith("https://"):
        raise ValueError(f"template URL must use HTTPS: {url}")
    request = Request(url, headers={"User-Agent": "CoreNovaMarketplaceValidator/1"})
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise ValueError(f"template returned HTTP {response.status}: {url}")
        return response.read().decode("utf-8")


def validate_plan(plan: dict[str, Any], region: str) -> None:
    changes = plan.get("ChangeSet")
    if not isinstance(changes, list) or not changes:
        raise ValueError("release plan has no ChangeSet entries")
    for change in changes:
        if change.get("ChangeType") != "AddDeliveryOptions":
            raise ValueError("only AddDeliveryOptions is supported")
        product_id = change["Entity"]["Identifier"]
        supported = live_product_instance_types(product_id, region)
        options = change["DetailsDocument"]["DeliveryOptions"]
        template_count = 0
        for option in options:
            details = (option.get("Details") or {}).get(
                "DeploymentTemplateDeliveryOptionDetails"
            )
            if details is None:
                continue
            template_count += 1
            url = details["Template"]
            template = load_template_text(download_template(url), url)
            candidates = validate_template_instance_types(template, supported, url)
            print(
                f"PASS\t{product_id}\t{url}\t{','.join(sorted(candidates))}"
            )
        if template_count != 2:
            raise ValueError(
                f"{product_id}: expected exactly two CloudFormation delivery options"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        validate_plan(plan, args.region)
    except Exception as exc:
        print(f"INSTANCE_TYPE_COMPATIBILITY_FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
