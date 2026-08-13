from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from submit_changeset import assert_eks_delivery_plan  # noqa: E402


def plan(option_count: int = 3) -> dict:
    source = {
        "AmiId": "ami-0123456789abcdef0",
        "AccessRoleArn": "arn:aws:iam::123456789012:role/Ingestion",
        "UserName": "ec2-user",
        "OperatingSystemName": "AMAZONLINUX",
        "OperatingSystemVersion": "Amazon Linux 2023",
    }
    options = [
        {"Details": {"AmiDeliveryOptionDetails": {"AmiSource": source}}},
        {
            "DeliveryOptionTitle": "Identity Relay - per-user AWS identity",
            "Details": {
                "DeploymentTemplateDeliveryOptionDetails": {
                    "Template": "https://assets.example.com/v1/identity-relay.yaml",
                    "ArchitectureDiagram": "https://assets.example.com/v1/identity-relay.png",
                    "TemplateSources": [{"ParameterName": "AmiId", "AmiSource": source}],
                }
            },
        },
        {
            "DeliveryOptionTitle": "Audited Workstation - streamed shell logs",
            "Details": {
                "DeploymentTemplateDeliveryOptionDetails": {
                    "Template": "https://assets.example.com/v1/audited-workstation.yaml",
                    "ArchitectureDiagram": "https://assets.example.com/v1/audited-workstation.png",
                    "TemplateSources": [{"ParameterName": "AmiId", "AmiSource": source}],
                }
            },
        },
    ][:option_count]
    return {
        "ChangeSet": [
            {
                "ChangeType": "AddDeliveryOptions",
                "Entity": {"Identifier": "prod-hapxotc2y7jmi"},
                "DetailsDocument": {"DeliveryOptions": options},
            }
        ]
    }


class SubmitGuardTests(unittest.TestCase):
    def test_accepts_complete_eks_plan(self) -> None:
        assert_eks_delivery_plan(plan())

    @mock.patch("submit_changeset.fail", side_effect=RuntimeError)
    def test_rejects_incomplete_eks_plan(self, _fail: mock.Mock) -> None:
        with self.assertRaises(RuntimeError):
            assert_eks_delivery_plan(plan(option_count=1))

    @mock.patch("submit_changeset.fail", side_effect=RuntimeError)
    def test_rejects_mutable_query_url(self, _fail: mock.Mock) -> None:
        value = plan()
        value["ChangeSet"][0]["DetailsDocument"]["DeliveryOptions"][1]["Details"]["DeploymentTemplateDeliveryOptionDetails"]["Template"] += "?versionId=1"
        with self.assertRaises(RuntimeError):
            assert_eks_delivery_plan(value)


if __name__ == "__main__":
    unittest.main()
