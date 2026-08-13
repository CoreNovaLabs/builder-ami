#!/usr/bin/env python3
"""Fail closed when EKS Marketplace delivery assets violate safety invariants."""

from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
from typing import Any

import yaml

from productlib import ROOT


ASSET_DIR = ROOT / "marketplace" / "eks-admin-bastion"
TEMPLATE_DIR = ASSET_DIR / "cloudformation"


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


def load_template(path: Path) -> dict[str, Any]:
    value = yaml.load(path.read_text(encoding="utf-8"), Loader=CloudFormationLoader)
    if not isinstance(value, dict):
        raise AssertionError(f"{path}: expected a mapping")
    return value


def resource(template: dict[str, Any], name: str, expected_type: str) -> dict[str, Any]:
    value = template["Resources"][name]
    assert value["Type"] == expected_type, f"{name}: expected {expected_type}"
    return value


def json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def validate_common(template: dict[str, Any], instance_name: str, sg_name: str) -> None:
    parameters = template["Parameters"]
    assert parameters["AmiId"]["Type"] == "AWS::EC2::Image::Id"
    assert parameters["InstanceArchitecture"]["Default"] == "x86_64"
    assert "RequireArchitectureCompatibleInstanceType" in template["Rules"]

    sg = resource(template, sg_name, "AWS::EC2::SecurityGroup")
    sg_properties = sg["Properties"]
    assert "SecurityGroupIngress" not in sg_properties, f"{sg_name}: embedded ingress found"

    instance = resource(template, instance_name, "AWS::EC2::Instance")["Properties"]
    interfaces = instance["NetworkInterfaces"]
    assert len(interfaces) == 1
    assert interfaces[0]["AssociatePublicIpAddress"] is False
    assert "SubnetId" not in instance and "SecurityGroupIds" not in instance
    metadata = instance["MetadataOptions"]
    assert metadata["HttpTokens"] == "required"
    assert metadata["HttpPutResponseHopLimit"] == 1
    ebs = instance["BlockDeviceMappings"][0]["Ebs"]
    assert ebs["Encrypted"] is True and ebs["VolumeType"] == "gp3"
    assert ebs["DeleteOnTermination"] is True

    ingress = resource(template, "ClusterApiIngress", "AWS::EC2::SecurityGroupIngress")
    ingress_properties = ingress["Properties"]
    assert ingress_properties["IpProtocol"] == "tcp"
    assert ingress_properties["FromPort"] == 443
    assert ingress_properties["ToPort"] == 443
    assert "CidrIp" not in ingress_properties and "CidrIpv6" not in ingress_properties
    assert "SourceSecurityGroupId" in ingress_properties


def validate_identity_relay(template: dict[str, Any]) -> None:
    validate_common(template, "RelayInstance", "RelaySecurityGroup")
    role = resource(template, "RelayRole", "AWS::IAM::Role")["Properties"]
    role_text = json_text(role).lower()
    assert "eks:" not in role_text, "identity relay EC2 role must not call EKS"
    assert "ec2:" not in role_text, "identity relay EC2 role must not call EC2"
    assert "amazonssmmanagedinstancecore" in role_text

    access_entries = [
        value
        for value in template["Resources"].values()
        if value["Type"] == "AWS::EKS::AccessEntry"
    ]
    assert len(access_entries) == 2
    for entry in access_entries:
        assert entry["Properties"]["PrincipalArn"] == {"Ref": "OperatorRoleArn"}
        ignored = entry["Metadata"]["cfn-lint"]["config"]["ignore_checks"]
        assert ignored == ["W1030"]
    assert template["Parameters"]["CreateOperatorAccessEntry"]["Default"] == "No"
    assert template["Parameters"]["OperatorRoleArn"]["Default"] == ""
    assert "RequireOperatorRoleWhenCreatingAccessEntry" in template["Rules"]
    assert template["Parameters"]["EksAccessPolicyName"]["Default"] == "AmazonEKSViewPolicy"
    assert template["Parameters"]["AccessScope"]["Default"] == "Namespace"


def validate_audited_workstation(template: dict[str, Any]) -> None:
    validate_common(template, "WorkstationInstance", "WorkstationSecurityGroup")
    assert template["Parameters"]["EksAccessPolicyName"]["Default"] == "AmazonEKSViewPolicy"
    assert template["Parameters"]["AccessScope"]["Default"] == "Namespace"
    assert template["Parameters"]["KubernetesNamespace"]["Default"] == "default"
    assert "RequireAcknowledgementForPrivilegedAccess" in template["Rules"]

    log_group = resource(template, "AuditLogGroup", "AWS::Logs::LogGroup")
    assert log_group["DeletionPolicy"] == "Retain"
    assert log_group["UpdateReplacePolicy"] == "Retain"
    session = resource(template, "AuditedSessionDocument", "AWS::SSM::Document")
    content = session["Properties"]["Content"]
    assert content["sessionType"] == "Standard_Stream"
    inputs = content["inputs"]
    assert inputs["cloudWatchStreamingEnabled"] is True
    assert inputs["runAsEnabled"] is True
    assert inputs["runAsDefaultUser"] == "corenova-operator"
    assert "IdleSessionTimeoutMinutes" in json_text(inputs)
    assert "MaxSessionDurationMinutes" in json_text(inputs)

    role = resource(template, "WorkstationRole", "AWS::IAM::Role")["Properties"]
    role_text = json_text(role)
    for required in ("eks:DescribeCluster", "logs:PutLogEvents", "AmazonSSMManagedInstanceCore"):
        assert required in role_text
    assert "iam:PassRole" not in role_text
    assert "sts:AssumeRole" not in json_text(role.get("Policies", []))


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    if len(data) != 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"{path}: invalid PNG header")
    return struct.unpack(">II", data[16:24])


def validate_diagrams() -> None:
    for stem in ("identity-relay-architecture", "audited-workstation-architecture"):
        svg = TEMPLATE_DIR / f"{stem}.svg"
        png = TEMPLATE_DIR / f"{stem}.png"
        assert svg.is_file() and png.is_file()
        assert png_dimensions(png) == (1100, 700), f"{png}: expected 1100x700"


def validate_client() -> None:
    client = ASSET_DIR / "client" / "corenova_eks_connect.py"
    text = client.read_text(encoding="utf-8")
    assert "AWS-StartPortForwardingSessionToRemoteHost" in text
    assert "tls-server-name" in text
    assert "certificate-authority-data" in text
    assert "shell=True" not in text
    assert "insecure-skip-tls-verify" not in text


def validate_operator_policies() -> None:
    policies = {
        "identity": ASSET_DIR / "iam" / "identity-relay-operator-policy.json",
        "audited": ASSET_DIR / "iam" / "audited-workstation-operator-policy.json",
    }
    loaded = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in policies.items()}
    identity_text = json_text(loaded["identity"])
    audited_text = json_text(loaded["audited"])
    assert "AWS-StartPortForwardingSessionToRemoteHost" in identity_text
    assert "eks:DescribeCluster" in identity_text
    assert "cloudformation:DescribeStacks" in identity_text
    assert "ssm:StartSession" in audited_text
    assert "ssmmessages:OpenDataChannel" in identity_text
    assert "ssmmessages:OpenDataChannel" in audited_text
    assert "SESSION_DOCUMENT_NAME" in audited_text
    for text in (identity_text, audited_text):
        assert '"Action": "*"' not in text
        assert '"Resource": "*"' not in text


def validate_ansible_profile() -> None:
    tasks = (ROOT / "ansible" / "roles" / "core" / "tasks" / "eks_admin_bastion.yml").read_text(
        encoding="utf-8"
    )
    doctor = (ROOT / "ansible" / "roles" / "core" / "files" / "corenova-eks-doctor").read_text(
        encoding="utf-8"
    )
    for required in (
        "name: corenova-operator",
        "password_lock: true",
        "src: corenova-eks-doctor",
        "- python3",
        "- screen",
    ):
        assert required in tasks
    assert "MIN_REMOTE_HOST_AGENT = (3, 1, 1374, 0)" in doctor
    assert "insecure" not in doctor.lower()


def validate_candidate_workflow() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ami-candidate.yml").read_text(
        encoding="utf-8"
    )
    for required in (
        "CoreNovaAmiBuilderRole",
        "CoreNovaEksBastionSmokeRunnerRole",
        "RUN_ONE_CANDIDATE_PIPELINE",
        "Run no-ingress SSM smoke test",
    ):
        assert required in workflow
    for forbidden in (
        "marketplace-catalog",
        "CoreNovaMarketplaceValidatorRole",
        "asset_base_url:",
        "--intent VALIDATE",
    ):
        assert forbidden not in workflow


def main() -> int:
    checks = (
        ("identity-relay", lambda: validate_identity_relay(load_template(TEMPLATE_DIR / "identity-relay.yaml"))),
        ("audited-workstation", lambda: validate_audited_workstation(load_template(TEMPLATE_DIR / "audited-workstation.yaml"))),
        ("architecture-diagrams", validate_diagrams),
        ("identity-relay-client", validate_client),
        ("operator-iam-policies", validate_operator_policies),
        ("ami-profile", validate_ansible_profile),
        ("candidate-workflow", validate_candidate_workflow),
    )
    failed = False
    for name, check in checks:
        try:
            check()
        except Exception as exc:
            failed = True
            print(f"FAIL\t{name}\t{exc}", file=sys.stderr)
        else:
            print(f"PASS\t{name}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
