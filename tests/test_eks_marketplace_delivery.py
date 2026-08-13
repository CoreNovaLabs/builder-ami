from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from package_eks_admin_delivery_assets import package  # noqa: E402
from render_marketplace_changeset import (  # noqa: E402
    build_change_set,
    eks_cloudformation_delivery_options,
    validate_asset_base_url,
)


class MarketplaceDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.product = {
            "architecture": "arm64",
            "recommended_instance_type": "t4g.small",
            "profile": "eks-admin-bastion",
            "entity_id": "prod-example",
            "title": "Example EKS Bastion",
            "ssh_username": "ec2-user",
            "scanning_port": 22,
            "operating_system_name": "AMAZONLINUX",
            "operating_system_version": "Amazon Linux 2023",
            "layout": "root-xfs",
            "filesystem": "xfs",
            "security_groups": [
                {
                    "ip_protocol": "tcp",
                    "from_port": 22,
                    "to_port": 22,
                    "ip_ranges": ["10.0.0.0/8"],
                }
            ],
            "_aws": {"marketplace_catalog": "AWSMarketplace"},
        }
        self.source = {
            "AmiId": "ami-0123456789abcdef0",
            "AccessRoleArn": "arn:aws:iam::123456789012:role/Ingestion",
            "UserName": "ec2-user",
            "ScanningPort": 22,
            "OperatingSystemName": "AMAZONLINUX",
            "OperatingSystemVersion": "Amazon Linux 2023",
        }

    def test_renders_both_cloudformation_modes(self) -> None:
        options = eks_cloudformation_delivery_options(
            self.product, self.source, "https://assets.example.com/releases/v1/"
        )
        self.assertEqual(len(options), 2)
        self.assertEqual(
            [option["DeliveryOptionTitle"].split(" - ")[0] for option in options],
            ["Identity Relay", "Audited Workstation"],
        )
        for option in options:
            details = option["Details"]["DeploymentTemplateDeliveryOptionDetails"]
            self.assertIn("/arm64/", details["Template"])
            self.assertIn("/docs/index.html", details["UsageInstructions"])
            template_source = details["TemplateSources"][0]
            self.assertEqual(template_source["ParameterName"], "AmiId")
            self.assertNotIn("ScanningPort", template_source["AmiSource"])

    def test_full_plan_has_three_consistent_sources(self) -> None:
        plan = build_change_set(
            product=self.product,
            ami_id=self.source["AmiId"],
            access_role_arn=self.source["AccessRoleArn"],
            include_eks_cloudformation=True,
            asset_base_url="https://assets.example.com/eks/v20260814-0123456789ab",
            version_title_override="v20260814",
        )
        options = plan["ChangeSet"][0]["DetailsDocument"]["DeliveryOptions"]
        self.assertEqual(len(options), 3)
        self.assertEqual(
            plan["ChangeSet"][0]["DetailsDocument"]["Version"]["VersionTitle"],
            "v20260814",
        )
        self.assertIn(
            "Version: v20260814",
            plan["ChangeSet"][0]["DetailsDocument"]["Version"]["ReleaseNotes"],
        )
        standalone = options[0]["Details"]["AmiDeliveryOptionDetails"]["AmiSource"]
        for option in options[1:]:
            source = option["Details"]["DeploymentTemplateDeliveryOptionDetails"]["TemplateSources"][0]["AmiSource"]
            for key in ("AmiId", "AccessRoleArn", "UserName", "OperatingSystemName", "OperatingSystemVersion"):
                self.assertEqual(source[key], standalone[key])

    def test_rejects_non_https_and_query_strings(self) -> None:
        for value in ("http://assets.example.com", "https://assets.example.com?v=1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_asset_base_url(value)

    def test_rejects_invalid_fixed_version(self) -> None:
        with self.assertRaises(ValueError):
            build_change_set(
                product=self.product,
                ami_id=self.source["AmiId"],
                access_role_arn=self.source["AccessRoleArn"],
                version_title_override="latest",
            )

    def test_package_locks_architecture_and_instance_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            stale = Path(directory) / "stale.txt"
            stale.write_text("must not survive packaging")
            manifest = package(Path(directory))
            self.assertTrue(manifest.is_file())
            self.assertFalse(stale.exists())
            metadata = __import__("json").loads(manifest.read_text())
            self.assertEqual(metadata["schema_version"], 2)
            self.assertIn("client/corenova_eks_connect.py", metadata["common"])
            self.assertIn("docs/index.html", metadata["common"])
            self.assertTrue((Path(directory) / "docs" / "quickstart.md").is_file())
            arm = (Path(directory) / "arm64" / "identity-relay.yaml").read_text()
            x86 = (Path(directory) / "x86_64" / "identity-relay.yaml").read_text()
            self.assertIn("AllowedValues: [arm64]", arm)
            self.assertIn("Default: t4g.micro", arm)
            self.assertIn("AllowedValues: [x86_64]", x86)
            self.assertIn("Default: t3.micro", x86)


if __name__ == "__main__":
    unittest.main()
