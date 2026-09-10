from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from productlib import assert_marketplace_product, product_by_key  # noqa: E402
from render_production_readiness_changeset import (  # noqa: E402
    feature_bullets,
    storage_description,
)
from render_public_metadata_updates import (  # noqa: E402
    PLANS,
    TITLE_OVERRIDES,
    render_change_set,
)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class ImageCurrencyTests(unittest.TestCase):
    def test_eks_toolchain_is_pinned_and_aws_cli_is_signature_verified(self) -> None:
        tasks = read("ansible/roles/core/tasks/eks_admin_bastion.yml")
        for value in (
            "2.36.42",
            "v1.31.14 v1.32.13 v1.33.13 v1.34.11 v1.35.8 v1.36.4",
            "v3.22.0",
            "v0.230.0",
            "v0.51.0",
            "v4.53.6",
            "v0.11.0",
        ):
            self.assertIn(value, tasks)
        self.assertNotIn("CORENOVA_KUBECTL_MINORS", tasks)
        self.assertIn("awscliv2.zip.sig", tasks)
        self.assertIn("gpg --batch", tasks)
        self.assertIn("FB5DB77FD5C118B80511ADA8A6310ACC4672475C", tasks)
        self.assertTrue(
            (ROOT / "ansible/roles/core/files/eks-admin-bastion/aws-cli-team.asc").is_file()
        )

    def test_gpu_driver_and_ai_container_versions_are_pinned(self) -> None:
        for path in (
            "ansible/roles/core/tasks/gpu_ubuntu.yml",
            "ansible/roles/core/tasks/ai_inference.yml",
            "ansible/roles/core/files/gpu-ubuntu/install-gpu.sh",
        ):
            source = read(path)
            self.assertIn("cuda-drivers-580", source)
            self.assertNotIn("cuda-drivers-550", source)

        compose = read("ansible/roles/core/files/ai-inference/compose/docker-compose.yml")
        self.assertIn("ollama/ollama:0.33.3", compose)
        self.assertIn("open-webui/open-webui:v0.11.3", compose)
        self.assertIn("vllm/vllm-openai:v0.29.0", compose)
        self.assertNotIn(":latest", compose)
        self.assertNotIn(":main", compose)
        self.assertTrue(
            (ROOT / "ansible/roles/core/files/ai-inference/compose/.env.example").is_file()
        )
        smoke = read("scripts/smoke_test_ami.sh")
        for value in ("^580\\.", "ollama/ollama:0.33.3", "open-webui:v0.11.3", "vllm-openai:v0.29.0"):
            self.assertIn(value, smoke)

    def test_redhat_automatic_updates_are_applied_and_smoke_tested(self) -> None:
        tasks = read("ansible/roles/core/tasks/main.yml")
        smoke = read("scripts/smoke_test_ami.sh")
        for value in ("upgrade_type", "download_updates", "apply_updates"):
            self.assertIn(value, tasks)
            self.assertIn(value, smoke)
        dnf_service = tasks.split("- name: Enable dnf automatic", 1)[1]
        dnf_service = dnf_service.split("\n- name:", 1)[0]
        self.assertNotIn("failed_when: false", dnf_service)
        self.assertIn("systemctl is-active --quiet dnf-automatic.timer", tasks)

    def test_packer_plugins_are_currently_pinned(self) -> None:
        packer = read("packer/marketplace-ami.pkr.hcl")
        self.assertIn('version = "= 1.8.2"', packer)
        self.assertIn('version = "= 1.1.6"', packer)

    def test_arm64_product_no_longer_advertises_unverified_64k_pages(self) -> None:
        product = product_by_key("amazon-linux-2023-arm64-64k")
        self.assertNotIn("64K", product["title"])
        self.assertEqual(product["filesystem"], "ext4")
        self.assertEqual(storage_description(product), "Standard Ext4 root volume.")
        self.assertFalse(any("64K" in bullet for bullet in feature_bullets(product)))

        entity_id = product["entity_id"]
        plan = PLANS[entity_id]
        self.assertNotIn("64K", plan.storage)
        self.assertFalse(any("64k" in keyword.lower() for keyword in plan.keywords))
        self.assertEqual(TITLE_OVERRIDES[entity_id], product["title"])

        live = {
            "DetailsDocument": {
                "Description": {
                    "ProductTitle": "Amazon Linux 2023 Graviton Hardened (ARM64, 64K-Page)"
                }
            }
        }
        with mock.patch("render_public_metadata_updates.describe_entity", return_value=live):
            change_set = render_change_set({"EntityId": entity_id})
        update = change_set["ChangeSet"][0]["DetailsDocument"]
        self.assertEqual(update["ProductTitle"], product["title"])
        self.assertNotIn("64K", str(update))

    def test_legacy_marketplace_title_is_accepted_only_during_migration(self) -> None:
        product = product_by_key("amazon-linux-2023-arm64-64k")
        old_title = "Amazon Linux 2023 Graviton Hardened (ARM64, 64K-Page)"
        self.assertEqual(product["accepted_live_titles"], [old_title])
        response = {
            "DetailsDocument": {"Description": {"ProductTitle": old_title}},
        }
        with mock.patch("productlib.run_aws", return_value=response):
            result = assert_marketplace_product(product)
        self.assertEqual(result["details"]["Description"]["ProductTitle"], old_title)


if __name__ == "__main__":
    unittest.main()
