import tempfile
import unittest
from pathlib import Path

from benchmark.full_runner import write_html_report, write_markdown_report, write_model_comparison


class FullRunnerTests(unittest.TestCase):
    def test_visual_and_comparison_outputs(self):
        rows = [{"run_id": "r1", "variant": "A53T", "ablation": "all_evidence", "model": "baseline", "completed": True, "gold_label": "vus", "json_schema_valid": True, "claim_checks": [], "top5_evidence_count": 0, "top5_variant_mentions": 0, "uncertainty_preserved": True, "runtime_seconds": 0.1, "external_api_failure": False, "stage_status": {"payload": "success"}}]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_html_report(rows, root / "report.html")
            write_markdown_report(rows, root / "report.md")
            write_model_comparison(rows, root / "models.csv")
            self.assertIn("Ablation comparison", (root / "report.html").read_text())
            self.assertIn("benchmark report", (root / "report.md").read_text())
            self.assertIn("baseline", (root / "models.csv").read_text())


if __name__ == "__main__":
    unittest.main()
