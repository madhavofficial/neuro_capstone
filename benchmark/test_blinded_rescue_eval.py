import csv
import tempfile
import unittest
from pathlib import Path

from benchmark.blinded_rescue_eval import load_rows, evaluate


class BlindedRescueEvaluationTests(unittest.TestCase):

    def make_csv(self, rows):
        temp = tempfile.NamedTemporaryFile(
            mode="w", newline="", suffix=".csv", delete=False,
            encoding="utf-8"
        )
        writer = csv.DictWriter(
            temp,
            fieldnames=[
                "gene", "variant", "label",
                "alphamissense_score", "structure_only_score"
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
        temp.close()
        self.addCleanup(Path(temp.name).unlink, missing_ok=True)
        return Path(temp.name)

    def valid_rows(self):
        return [
            {
                "gene": "TTR", "variant": "V50M",
                "label": "pathogenic",
                "alphamissense_score": "0.2",
                "structure_only_score": "0.9",
            },
            {
                "gene": "TTR", "variant": "T139M",
                "label": "benign",
                "alphamissense_score": "0.8",
                "structure_only_score": "0.1",
            },
            {
                "gene": "SNCA", "variant": "A53T",
                "label": "pathogenic",
                "alphamissense_score": "0.9",
                "structure_only_score": "0.8",
            },
            {
                "gene": "SNCA", "variant": "G51D",
                "label": "benign",
                "alphamissense_score": "0.1",
                "structure_only_score": "0.2",
            },
        ]

    def test_loads_valid_blinded_rows(self):
        path = self.make_csv(self.valid_rows())
        rows = load_rows(path)
        self.assertEqual(len(rows), 4)

    def test_rejects_single_class_dataset(self):
        rows = self.valid_rows()
        rows = [dict(r, label="pathogenic") for r in rows]
        path = self.make_csv(rows)
        with self.assertRaisesRegex(ValueError, "both pathogenic and benign"):
            load_rows(path)

    def test_rejects_unsettled_labels(self):
        rows = self.valid_rows()
        rows[0]["label"] = "unsettled"
        path = self.make_csv(rows)
        with self.assertRaisesRegex(ValueError, "label must be"):
            load_rows(path)

    def test_rejects_duplicate_variants(self):
        rows = self.valid_rows()
        rows[1]["gene"] = rows[0]["gene"]
        rows[1]["variant"] = rows[0]["variant"]
        path = self.make_csv(rows)
        with self.assertRaisesRegex(ValueError, "Duplicate variant"):
            load_rows(path)

    def test_rejects_missing_scores(self):
        rows = self.valid_rows()
        rows[0]["structure_only_score"] = ""
        path = self.make_csv(rows)
        with self.assertRaisesRegex(ValueError, "invalid numeric score"):
            load_rows(path)

    def test_calculates_perfect_structure_auc(self):
        rows = load_rows(self.make_csv(self.valid_rows()))
        result = evaluate(rows, 0.3, 0.5, 200, 42)
        self.assertEqual(result["structure_only_auroc"], 1.0)
        self.assertEqual(result["n_pathogenic"], 2)
        self.assertEqual(result["n_benign"], 2)

    def test_counts_low_alphamissense_rescues(self):
        rows = load_rows(self.make_csv(self.valid_rows()))
        result = evaluate(rows, 0.3, 0.5, 200, 42)
        self.assertEqual(result["low_alphamissense_pathogenic_count"], 1)
        self.assertEqual(result["rescued_false_negative_count"], 1)
        self.assertEqual(
            result["rescued_variants"],
            [{"gene": "TTR", "variant": "V50M"}],
        )

    def test_labels_are_not_used_as_features(self):
        rows = load_rows(self.make_csv(self.valid_rows()))
        result = evaluate(rows, 0.3, 0.5, 200, 42)
        self.assertIn("never predictors", result["feature_policy"])
        self.assertNotIn("clinvar_label", rows[0])
        self.assertNotIn("label", rows[0]["gene"])

if __name__ == "__main__":
    unittest.main()
