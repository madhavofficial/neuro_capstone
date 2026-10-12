import json
import tempfile
import unittest
from pathlib import Path

from benchmark import benchmark


class BenchmarkTests(unittest.TestCase):
    def test_prediction_normalisation_is_conservative(self):
        self.assertEqual(benchmark.normalise_prediction("conflicting classifications of pathogenicity"), "vus")
        self.assertEqual(benchmark.normalise_prediction({"prediction": "benign", "conclusion": "pathogenic"}), "benign")
        self.assertEqual(benchmark.normalise_prediction("evidence supports a likely pathogenic classification"), "pathogenic")
        self.assertEqual(benchmark.normalise_prediction("insufficient evidence"), "vus")

    def test_agreement_uses_synthesis_prediction_not_clinvar_string(self):
        rows = [{"completed": True, "gold_label": "benign", "prediction": "pathogenic", "clinical_agreement": False,
                 "top5_evidence_count": 0, "top5_variant_mentions": 0, "claim_checks": [],
                 "json_schema_valid": True, "runtime_seconds": 1}]
        metrics = benchmark.calculate_metrics(rows)
        self.assertEqual(metrics["pathogenic_benign_agreement"], 0.0)
        self.assertEqual(metrics["prediction_by_class"]["benign"]["agreement"], 0.0)

    def test_payload_schema_and_vus_metric(self):
        payload = {"status": "LOW_CONFIDENCE", "query": "SNCA A53T", "evidence": []}
        self.assertEqual(benchmark.validate_payload(payload), (True, []))
        rows = [{"completed": True, "gold_label": "vus", "uncertainty_preserved": True,
                 "top5_evidence_count": 0, "top5_variant_mentions": 0,
                 "claim_checks": [], "json_schema_valid": True, "runtime_seconds": 1}]
        self.assertEqual(benchmark.calculate_metrics(rows)["vus_uncertainty_preservation"], 1.0)

    def test_runner_writes_payload_and_row(self):
        target = {"variant_id": "x", "gene": "SNCA", "variant": "A53T", "label": "vus"}
        def fake_pipeline(gene, variant, *, ablation):
            return {"status": "LOW_CONFIDENCE", "query": f"{gene} {variant}", "evidence": [], "clinical_label": "Conflicting classifications of pathogenicity"}
        with tempfile.TemporaryDirectory() as directory:
            row = benchmark.run_one(target, "all_evidence", fake_pipeline, benchmark._default_synthesis, Path(directory))
            self.assertTrue(row["completed"])
            self.assertTrue(row["uncertainty_preserved"])
            self.assertTrue(row["json_schema_valid"])
            self.assertEqual(row["prediction"], "vus")


if __name__ == "__main__":
    unittest.main()
