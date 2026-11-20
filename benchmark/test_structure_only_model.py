import csv
import json
import tempfile
import unittest
from pathlib import Path

from benchmark.structure_only_model import load_inputs, evaluate, STRUCTURAL_KEYS


class StructureOnlyModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.features_path = self.root / "features.json"
        self.labels_path = self.root / "labels.csv"

    def write_inputs(self, *, forbidden=False, missing_am=False):
        features = []
        labels = []
        for gene_index in range(10):
            gene = f"GENE{gene_index}"
            for class_index, label in enumerate(("benign", "pathogenic")):
                variant = f"V{gene_index}{class_index}"
                structural = {
                    "exposure": "Buried" if class_index == 0 else "Exposed",
                    "sasa": 20.0 + 50.0 * class_index,
                    "secondary_structure": "Helix",
                    "plddt_confidence": 90.0,
                    "delta_volume": 2.0 + 20.0 * class_index,
                    "delta_hydrophobicity": -1.0 + class_index,
                    "delta_charge": float(class_index),
                    "backbone_strain": "None",
                    "salt_bridges_lost": [],
                    "disulfides_lost": [],
                    "h_bonds_lost_est": float(class_index),
                    "interface_contacts_lost": 0.0,
                    "delta_aggregation": float(class_index),
                    "monomer_ddg": None,
                }
                row = {
                    "gene": gene, "variant": variant,
                    "alphamissense_score": None if missing_am else (0.2 if class_index else 0.8),
                    "structural_features": structural,
                }
                if forbidden:
                    row["clinical_label"] = label
                features.append(row)
                labels.append({"gene": gene, "variant": variant, "label": label})
        self.features_path.write_text(json.dumps(features), encoding="utf-8")
        with self.labels_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["gene", "variant", "label"])
            writer.writeheader()
            writer.writerows(labels)

    def test_loads_independent_labels_and_structural_features(self):
        self.write_inputs()
        rows = load_inputs(self.features_path, self.labels_path)
        self.assertEqual(len(rows), 20)
        self.assertEqual(set(rows[0]) & {"label"}, {"label"})
        self.assertEqual(set(STRUCTURAL_KEYS) - set(rows[0]), set())

    def test_rejects_clinical_fields_in_feature_json(self):
        self.write_inputs(forbidden=True)
        with self.assertRaisesRegex(ValueError, "forbidden clinical/ClinVar"):
            load_inputs(self.features_path, self.labels_path)

    def test_grouped_oof_evaluation(self):
        self.write_inputs()
        rows = load_inputs(self.features_path, self.labels_path)
        result = evaluate(rows, folds=5, iterations=200, seed=42,
                          am_low_cutoff=0.3, structure_positive_cutoff=0.5)
        self.assertEqual(result["n_variants"], 20)
        self.assertEqual(result["n_genes"], 10)
        self.assertEqual(len(result["out_of_fold_predictions"]), 20)
        self.assertGreaterEqual(result["structure_only_auroc_oof"], 0.0)
        self.assertLessEqual(result["structure_only_auroc_oof"], 1.0)
        self.assertIn("gene-grouped", result["method"])

    def test_missing_alphamissense_is_counted_not_imputed(self):
        self.write_inputs(missing_am=True)
        rows = load_inputs(self.features_path, self.labels_path)
        result = evaluate(rows, folds=5, iterations=200, seed=42,
                          am_low_cutoff=0.3, structure_positive_cutoff=0.5)
        self.assertEqual(result["n_missing_alphamissense"], 20)
        self.assertEqual(result["low_alphamissense_pathogenic_count"], 0)

    def test_accepts_humsavar_abbreviations(self):
        self.write_inputs()
        with self.labels_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            row["label"] = "LP" if row["label"] == "pathogenic" else "LB"
        with self.labels_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["gene", "variant", "label"])
            writer.writeheader()
            writer.writerows(rows)
        self.assertEqual(len(load_inputs(self.features_path, self.labels_path)), 20)


if __name__ == "__main__":
    unittest.main()
