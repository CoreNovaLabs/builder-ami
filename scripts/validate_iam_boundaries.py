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
    source_image = next(
        (
            statement
            for statement in run_statements
            if statement.get("Sid") == "UseAmazonAmi"
        ),
        None,
    )
    if source_image is None or string_equals(source_image).get("aws:ResourceAccount") != "137112412989":
        fail("builder does not restrict source AMIs to the Amazon Linux publisher account")
    if "ec2:Owner" in json.dumps(source_image):
        fail("builder source AMI must use the numeric aws:ResourceAccount condition")
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
    if image_statement is None or string_equals(image_statement).get("aws:ResourceAccount") != "582920575154":
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


def validate_instance_publisher() -> None:
    policy = load("marketplace-instance-publisher-policy.json")
    trust = load("marketplace-instance-publisher-trust-policy.json")
    rendered = json.dumps(policy)
    for required in (
        "prod-hapxotc2y7jmi",
        "prod-nspz2g6ki6qvo",
        "offer-2izpqagw3tftq",
        "offer-2n3inrntp75ye",
        "AddInstanceTypes",
        "AddDimensions",
        "UpdatePricingTerms",
    ):
        if required not in rendered:
            fail(f"instance publisher boundary is missing {required}")
    for forbidden in (
        "AddDeliveryOptions",
        "AddRegions",
        "UpdateInformation",
        "UpdateVisibility",
        "ReleaseProduct",
        "ReleaseOffer",
    ):
        if forbidden in rendered:
            fail(f"instance publisher unexpectedly allows {forbidden}")
    trust_rendered = json.dumps(trust)
    if "arn:aws:iam::582920575154:root" not in trust_rendered:
        fail("instance publisher trust is not pinned to the seller root principal")
    if "aws:MultiFactorAuthPresent" not in trust_rendered:
        fail("instance publisher trust does not require MFA")


def validate_eks_delivery_release_roles() -> None:
    asset = load("marketplace-asset-publisher-policy.json")
    asset_rendered = json.dumps(asset)
    for required in (
        "corenova-marketplace-assets-582920575154",
        "eks-admin-bastion/*",
        "s3:PutObject",
        "s3:DeleteObject",
    ):
        if required not in asset_rendered:
            fail(f"asset publisher boundary is missing {required}")
    delete_statements = [
        statement
        for statement in asset.get("Statement") or []
        if "s3:DeleteObject" in actions(statement)
    ]
    if not delete_statements or any(item.get("Effect") != "Deny" for item in delete_statements):
        fail("asset publisher must explicitly deny object deletion")

    delivery = load("marketplace-delivery-publisher-policy.json")
    delivery_rendered = json.dumps(delivery)
    for required in (
        "prod-hapxotc2y7jmi",
        "prod-nspz2g6ki6qvo",
        "AddDeliveryOptions",
        "aws-marketplace:Intent",
        "APPLY",
        "CoreNovaMarketplaceAmiIngestion",
    ):
        if required not in delivery_rendered:
            fail(f"delivery publisher boundary is missing {required}")
    for forbidden in (
        "RestrictDeliveryOptions",
        "UpdateDeliveryOptions",
        "UpdateInformation",
        "UpdateVisibility",
        "UpdatePricingTerms",
        "ReleaseProduct",
        "ReleaseOffer",
    ):
        if forbidden in delivery_rendered:
            fail(f"delivery publisher unexpectedly allows {forbidden}")

    runner = load("eks-delivery-e2e-policy.json")
    runner_actions = {
        action
        for statement in runner.get("Statement") or []
        if statement.get("Effect") == "Allow"
        for action in actions(statement)
    }
    for forbidden in ("ec2:*", "eks:*", "iam:*", "cloudformation:*"):
        if forbidden in runner_actions:
            fail(f"E2E runner contains broad action {forbidden}")
    runner_rendered = json.dumps(runner)
    for required in (
        "CoreNovaEksDeliveryE2ECloudFormationRole",
        "ssm:resourceTag/Purpose",
        "eks-delivery-e2e",
        "AWS-StartPortForwardingSessionToRemoteHost",
    ):
        if required not in runner_rendered:
            fail(f"E2E runner boundary is missing {required}")

    service = load("eks-delivery-e2e-cloudformation-policy.json")
    service_rendered = json.dumps(service)
    if '"Action": "ec2:*"' in service_rendered or '"Action": "eks:*"' in service_rendered:
        fail("E2E CloudFormation service policy contains a broad write wildcard")
    for required in (
        "iam:CreateServiceLinkedRole",
        "eks.amazonaws.com",
        "corenova-eks-e2e-*",
        "corenova-audited-e2e-*",
    ):
        if required not in service_rendered:
            fail(f"E2E CloudFormation policy is missing {required}")
    log_metadata = [
        statement
        for statement in service.get("Statement") or []
        if statement.get("Sid") == "ReadE2ELogGroupMetadata"
    ]
    if len(log_metadata) != 1:
        fail("E2E CloudFormation policy must have one log metadata statement")
    metadata_statement = log_metadata[0]
    if metadata_statement.get("Resource") != "*":
        fail("logs:DescribeLogGroups requires Resource *")
    if set(actions(metadata_statement)) != {"logs:DescribeLogGroups"}:
        fail("the wildcard log metadata statement must remain read-only")
    if metadata_statement.get("Condition") != {
        "StringEquals": {"aws:RequestedRegion": "us-east-1"}
    }:
        fail("the wildcard log metadata statement must remain region scoped")
    audit_logs = [
        statement
        for statement in service.get("Statement") or []
        if statement.get("Sid") == "ManageE2EAuditLogs"
    ]
    if len(audit_logs) != 1:
        fail("E2E CloudFormation policy must have one audit-log statement")
    audit_statement = audit_logs[0]
    if audit_statement.get("Resource") != (
        "arn:aws:logs:us-east-1:582920575154:log-group:"
        "/corenova/eks-ssm-bastion/corenova-audited-e2e-*:*"
    ):
        fail("E2E audit-log actions must remain prefix scoped")
    audit_metadata = [
        statement
        for statement in service.get("Statement") or []
        if statement.get("Sid") == "ReadE2EAuditLogResourceMetadata"
    ]
    if len(audit_metadata) != 1:
        fail("E2E CloudFormation policy must have one audit-log resource metadata statement")
    audit_metadata_statement = audit_metadata[0]
    if set(actions(audit_metadata_statement)) != {
        "logs:ListTagsForResource",
        "logs:DescribeIndexPolicies",
    }:
        fail("the audit-log resource metadata statement must remain read-only")
    if audit_metadata_statement.get("Resource") != (
        "arn:aws:logs:us-east-1:582920575154:log-group:"
        "/corenova/eks-ssm-bastion/corenova-audited-e2e-*"
    ):
        fail("E2E audit-log resource metadata reads must use the prefix-scoped log-group ARN")

    main_trust = json.dumps(load("github-main-trust-policy.json"))
    production_trust = json.dumps(load("github-marketplace-production-trust-policy.json"))
    immutable_main = "repo:CoreNovaLabs@283825262/builder-ami@1301293394:ref:refs/heads/main"
    if immutable_main not in main_trust:
        fail("delivery operational roles are not pinned to immutable repository main")
    production_subject = "repo:CoreNovaLabs@283825262/builder-ami@1301293394:environment:marketplace-production"
    if production_subject not in production_trust or "refs/heads/main" in production_trust:
        fail("delivery publisher trust is not isolated to marketplace-production")


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
    validate_instance_publisher()
    validate_eks_delivery_release_roles()
    validate_terraform_trust()
    print("IAM_BOUNDARIES_OK")


if __name__ == "__main__":
    main()
