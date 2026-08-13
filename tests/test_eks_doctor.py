from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DOCTOR_PATH = ROOT / "ansible" / "roles" / "core" / "files" / "corenova-eks-doctor"
LOADER = importlib.machinery.SourceFileLoader("corenova_eks_doctor", str(DOCTOR_PATH))
SPEC = importlib.util.spec_from_loader("corenova_eks_doctor", LOADER)
assert SPEC and SPEC.loader
doctor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(doctor)


class VersionTests(unittest.TestCase):
    def test_parses_agent_versions(self) -> None:
        self.assertEqual(doctor.parse_version("SSM Agent version: 3.3.3050.0"), (3, 3, 3050, 0))
        self.assertEqual(doctor.parse_version("amazon-ssm-agent version 3.1.1374"), (3, 1, 1374, 0))

    def test_rejects_non_versions(self) -> None:
        self.assertIsNone(doctor.parse_version("version unknown"))


if __name__ == "__main__":
    unittest.main()
