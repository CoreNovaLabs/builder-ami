#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IAM = ROOT / "marketplace" / "eks-admin-bastion" / "iam"


def load(name: str) -> dict:
    return json.loads((IAM / name).read_text(encoding="utf-8"))


def actions(statement: dict) -> list[str]:
    value = statement.get("Action") or []
    return [value] if isinstance(value, str) else list(value)


def resources(statement: dict) -> list[str]:
    value = statement.get("Resource") or []
    return [value] if isinstance(value, str) else list(value)


def string_equals(statement: dict) -> dict:
    return (statement.get("Condition") or {}).get("StringEquals") or {}


def fail(message: str) -> None:
    raise SystemExit(f"IAM_BOUNDARY_ERROR: {message}")


def validate_builder() -> None:
    path = IAM / "ami-builder-policy.json"
    policy = load(path.name)
    compact = json.dumps(policy, separators=(",", ":"))
    if len(compact) > 6144:
        fail(f"builder managed policy is {len(compact)} characters; limit is 6144")
    for statement in policy.get("Statement") or []:
        if statement.get("Effect") != "Allow" or statement.get("Resource") != "*":
            continue
        ec2_actions = [item for item in actions(statement) if item.startswith("ec2:")]
        if any(not item.startswith("ec2:Describe") for item in ec2_actions):
            fail(f"builder EC2 write action has Resource '*': {ec2_actions}")
    run_statements = [
        statement
        for statement in policy.get("Statement") or []
        if "ec2:RunInstances" in actions(statement)
    ]
    rendered = json.dumps(run_statements)
    for required in (
        "137112412989",
        "subnet-015304a4430329088",
        "t3.medium",
        "t4g.medium",
        "aws:RequestTag/Project",
        "aws:RequestTag/Purpose",
    ):
        if required not in rendered:
            fail(f"builder RunInstances boundary is missing {required}")
    if "arn:aws:ec2:us-east-1::image/*" not in rendered:
        fail("builder must use the accountless EC2 image ARN format")
    policy_rendered = json.dumps(policy)
    if "arn:aws:ec2:us-east-1::snapshot/*" not in policy_rendered:
        fail("builder must use the accountless EC2 snapshot ARN format")
    for invalid in (
        "arn:aws:ec2:us-east-1:582920575154:image/*",
        "arn:aws:ec2:us-east-1:582920575154:snapshot/*",
    ):
        if invalid in policy_rendered:
            fail(f"builder uses an invalid account-qualified ARN: {invalid}")
    expected_instance = "arn:aws:ec2:us-east-1:582920575154:instance/*"
    type_limited = []
    for statement in run_statements:
        if "ec2:InstanceType" not in string_equals(statement):
            continue
        type_limited.append(statement)
        if resources(statement) != [expected_instance]:
            fail("builder applies ec2:InstanceType to a non-instance resource")
    if len(type_limited) != 1:
        fail("builder must have exactly one instance-type-limited RunInstances statement")


def validate_smoke_core() -> None:
    policy = load("ssm-smoke-instance-core-policy.json")
    granted = {
        action
        for statement in policy.get("Statement") or []
        if statement.get("Effect") == "Allow"
        for action in actions(statement)
    }
    forbidden = {
        "ssm:GetParameter",
        "ssm:GetParameters",
        "ssm:GetParametersByPath",
    }
    present = sorted(forbidden & granted)
    if present:
        fail(f"smoke instance core can read Parameter Store: {present}")
    required = {
        "ssm:UpdateInstanceInformation",
        "ssmmessages:CreateControlChannel",
        "ssmmessages:OpenControlChannel",
        "ssmmessages:CreateDataChannel",
        "ssmmessages:OpenDataChannel",
    }
    missing = sorted(required - granted)
    if missing:
        fail(f"smoke instance core is missing SSM channel actions: {missing}")


def validate_smoke_runner() -> None:
    policy = load("ssm-smoke-runner-policy.json")
    rendered = json.dumps(policy)
    for required in (
        "vpc-0e54efb692e4f3ee6",
        "subnet-015304a4430329088",
        "ec2:ResourceTag/Marketplace",
        "t3.small",
        "t4g.small",
        "CoreNovaEksBastionSmokeInstanceRole",
    ):
        if required not in rendered:
            fail(f"smoke runner boundary is missing {required}")
    if "arn:aws:ec2:us-east-1::image/*" not in rendered:
        fail("smoke runner must use the accountless EC2 image ARN format")
    if "arn:aws:ec2:us-east-1:582920575154:image/*" in rendered:
        fail("smoke runner uses an invalid account-qualified EC2 image ARN")
    image_statement = next(
        (
            statement
            for statement in policy.get("Statement") or []
            if statement.get("Sid") == "UseCandidateImage"
        ),
        None,
    )
    if image_statement is None or string_equals(image_statement).get("ec2:Owner") != "582920575154":
        fail("smoke runner does not restrict candidate AMIs to the seller account")
    expected_instance = "arn:aws:ec2:us-east-1:582920575154:instance/*"
    type_limited = []
    for statement in policy.get("Statement") or []:
        if "ec2:RunInstances" not in actions(statement):
            continue
        if "ec2:InstanceType" not in string_equals(statement):
            continue
        type_limited.append(statement)
        if resources(statement) != [expected_instance]:
            fail("smoke runner applies ec2:InstanceType to a non-instance resource")
    if len(type_limited) != 1:
        fail("smoke runner must have exactly one instance-type-limited RunInstances statement")


def validate_observer() -> None:
    policy = load("marketplace-observer-policy.json")
    allowed = {
        "ce:GetCostAndUsage",
        "ce:GetCostForecast",
        "ec2:DescribeAddresses",
        "ec2:DescribeImages",
        "ec2:DescribeInstances",
        "ec2:DescribeNatGateways",
        "ec2:DescribeNetworkInterfaces",
        "ec2:DescribeRegions",
        "ec2:DescribeSnapshots",
        "ec2:DescribeVolumes",
        "ec2:DescribeVpcEndpoints",
        "aws-marketplace:ListChangeSets",
        "aws-marketplace:DescribeChangeSet",
        "aws-marketplace:DescribeEntity",
        "aws-marketplace:SearchAgreements",
    }
    granted = {
        action
        for statement in policy.get("Statement") or []
        if statement.get("Effect") == "Allow"
        for action in actions(statement)
    }
    unexpected = sorted(granted - allowed)
    if unexpected:
        fail(f"observer has unexpected actions: {unexpected}")


def validate_terraform_trust() -> None:
    main = (
        ROOT / "infra" / "terraform" / "eks-admin-bastion-operator-roles" / "main.tf"
    ).read_text(encoding="utf-8")
    variables = (
        ROOT
        / "infra"
        / "terraform"
        / "eks-admin-bastion-operator-roles"
        / "variables.tf"
    ).read_text(encoding="utf-8")
    expected = (
        "repo:CoreNovaLabs@283825262/"
        "builder-ami@1301293394:ref:refs/heads/main"
    )
    if expected not in variables:
        fail("Terraform does not pin the immutable GitHub main subject")
    if "publisher = {" in main:
        fail("GitHub OIDC Terraform still creates a publisher role")
    if "AmazonSSMManagedInstanceCore" in main:
        fail("Terraform still attaches the AWS-managed SSM core policy")
    required_reference = "aws_iam_policy.smoke_instance_core.arn"
    if main.count(required_reference) < 2:
        fail("custom smoke core must be both attachment and permissions boundary")


def main() -> None:
    validate_builder()
    validate_smoke_core()
    validate_smoke_runner()
    validate_observer()
    validate_terraform_trust()
    print("IAM_BOUNDARIES_OK")


if __name__ == "__main__":
    main()
