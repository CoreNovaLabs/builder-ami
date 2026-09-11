import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "eks-delivery-e2e.yml"


class EksE2ECostGateTest(unittest.TestCase):
    def test_ceiling_matches_the_global_warning_line(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        match = re.search(r"--mode cost --max-projected (\d+)", workflow)

        self.assertIsNotNone(match)
        ceiling = int(match.group(1))
        self.assertEqual(ceiling, 20)


if __name__ == "__main__":
    unittest.main()
