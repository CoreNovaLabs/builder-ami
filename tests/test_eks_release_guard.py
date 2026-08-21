from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from compose_eks_release_changeset import compose  # noqa: E402
from submit_eks_delivery_release import assert_release  # noqa: E402
from test_eks_submit_guard import plan as product_plan  # noqa: E402


class ReleaseGuardTests(unittest.TestCase):
    def plans(self, directory: Path) -> tuple[Path, Path]:
        items = []
        for name, entity in (("x86", "prod-hapxotc2y7jmi"), ("arm", "prod-nspz2g6ki6qvo")):
            value = product_plan()
            value["Catalog"] = "AWSMarketplace"
            value["ChangeSet"][0]["Entity"]["Type"] = "AmiProduct@1.0"
            value["ChangeSet"][0]["Entity"]["Identifier"] = entity
            value["ChangeSet"][0]["DetailsDocument"]["Version"] = {"VersionTitle": "v20260814"}
            path = directory / f"{name}.json"
            path.write_text(json.dumps(value))
            items.append(path)
        return items[0], items[1]

    def test_compose_and_evidence_binding(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            paths = self.plans(directory)
            combined = compose(list(paths))
            release = directory / "release.json"
            release.write_text(json.dumps(combined))
            digest = hashlib.sha256(release.read_bytes()).hexdigest()
            evidence = directory / "evidence.json"
            evidence.write_text(json.dumps({
                "status": "SUCCEEDED",
                "commit": "a" * 40,
                "plan_sha256": digest,
                "change_set_id": "example123-validated",
            }))
            with mock.patch.dict("os.environ", {"CORENOVA_PRODUCTS_FILE": "products.candidates.yaml"}):
                result = assert_release(release, evidence, "a" * 40)
            self.assertEqual(len(result["ChangeSet"]), 2)

    @mock.patch("submit_eks_delivery_release.fail", side_effect=RuntimeError)
    def test_rejects_plan_changed_after_validation(self, _fail: mock.Mock) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            paths = self.plans(directory)
            release = directory / "release.json"
            release.write_text(json.dumps(compose(list(paths))))
            evidence = directory / "evidence.json"
            evidence.write_text(json.dumps({
                "status": "SUCCEEDED",
                "commit": "a" * 40,
                "plan_sha256": "0" * 64,
                "change_set_id": "example123-validated",
            }))
            with mock.patch.dict("os.environ", {"CORENOVA_PRODUCTS_FILE": "products.candidates.yaml"}):
                with self.assertRaises(RuntimeError):
                    assert_release(release, evidence, "a" * 40)

    @mock.patch("submit_eks_delivery_release.fail", side_effect=RuntimeError)
    def test_rejects_invalid_catalog_change_set_id(self, _fail: mock.Mock) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            paths = self.plans(directory)
            release = directory / "release.json"
            release.write_text(json.dumps(compose(list(paths))))
            evidence = directory / "evidence.json"
            evidence.write_text(json.dumps({
                "status": "SUCCEEDED",
                "commit": "a" * 40,
                "plan_sha256": hashlib.sha256(release.read_bytes()).hexdigest(),
                "change_set_id": "change-set/contains/slashes",
            }))
            with mock.patch.dict("os.environ", {"CORENOVA_PRODUCTS_FILE": "products.candidates.yaml"}):
                with self.assertRaises(RuntimeError):
                    assert_release(release, evidence, "a" * 40)


if __name__ == "__main__":
    unittest.main()
