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

    def test_unsettled_variants_are_excluded_from_agreement_metrics(self):
        rows = [
            {
                "completed": True, "gold_label": "pathogenic", "prediction": "pathogenic",
                "top5_evidence_count": 0, "top5_variant_mentions": 0,
                "claim_checks": [], "json_schema_valid": True, "runtime_seconds": 1,
            },
            {
                "completed": True, "gold_label": "unsettled", "prediction": "pathogenic",
                "top5_evidence_count": 0, "top5_variant_mentions": 0,
                "claim_checks": [], "json_schema_valid": True, "runtime_seconds": 1,
            },
            {
                "completed": True, "gold_label": "unsettled", "prediction": "benign",
                "top5_evidence_count": 0, "top5_variant_mentions": 0,
                "claim_checks": [], "json_schema_valid": True, "runtime_seconds": 1,
            },
        ]
        metrics = benchmark.calculate_metrics(rows)
        self.assertEqual(metrics["n_unsettled_excluded"], 2)
        self.assertEqual(metrics["prediction_accuracy"], 1.0)
        self.assertEqual(metrics["pathogenic_benign_agreement"], 1.0)
        self.assertEqual(metrics["prediction_by_class"]["pathogenic"]["n"], 1)
        self.assertEqual(metrics["prediction_by_class"]["benign"]["n"], 0)

    def test_checked_in_gold_set_uses_published_classes_with_sources(self):
        gold_path = benchmark.DEFAULT_DIR / "gold_variants.csv"
        rows = benchmark.load_gold(gold_path)
        by_id = {row["variant_id"]: row for row in rows}
        for vid in ("mapt-g272v", "mapt-n279k", "ttr-v20i", "ttr-a25t", "ttr-v30a", "ttr-a45t"):
            self.assertEqual(by_id[vid]["label"], "pathogenic", vid)
            self.assertTrue(by_id[vid]["label_source"].strip(), vid)
        for vid in ("ttr-t139m", "ttr-g26s"):
            self.assertEqual(by_id[vid]["label"], "benign", vid)
            self.assertTrue(by_id[vid]["label_source"].strip(), vid)
        unsettled = [row["variant_id"] for row in rows if row["label"] == "unsettled"]
        self.assertEqual(len(unsettled), 9)
        for vid in ("snca-h50q", "snca-a53v", "snca-v15a"):
            self.assertIn(vid, unsettled)

    def test_load_gold_requires_label_source_on_settled_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "gold.csv"
            csv_path.write_text(
                "variant_id,gene,variant,label,label_source,clinvar_variation_id,review_status,condition,source_url,date_retrieved\n"
                "snca-a53t,SNCA,A53T,pathogenic,,14007,retrieved,PD,https://example.org,2026-08-17\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                benchmark.load_gold(csv_path)


if __name__ == "__main__":
    unittest.main()
