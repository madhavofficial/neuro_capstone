import csv
import json
import tempfile
import unittest
from pathlib import Path

from benchmark.structure_only_model import (
    load_inputs, evaluate, STRUCTURAL_KEYS, _cluster_bootstrap_auc,
)


class StructureOnlyModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.features_path = self.root / "features.json"
        self.labels_path = self.root / "labels.csv"

    def write_inputs(self, *, forbidden=False, missing_am=False,
                     all_missing_ddg=True):
        features, labels = [], []
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
                    "monomer_ddg": None if all_missing_ddg else float(class_index),
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
        self.assertEqual(set(STRUCTURAL_KEYS) - set(rows[0]), set())

    def test_rejects_clinical_fields_in_feature_json(self):
        self.write_inputs(forbidden=True)
        with self.assertRaisesRegex(ValueError, "forbidden clinical/ClinVar"):
            load_inputs(self.features_path, self.labels_path)

    def test_grouped_oof_evaluation_and_cluster_interval(self):
        self.write_inputs()
        rows = load_inputs(self.features_path, self.labels_path)
        result = evaluate(rows, folds=5, iterations=200, seed=42,
                          am_low_cutoff=0.3, structure_positive_cutoff=0.5)
        self.assertEqual(result["n_variants"], 20)
        self.assertEqual(result["n_genes"], 10)
        self.assertEqual(len(result["out_of_fold_predictions"]), 20)
        self.assertGreaterEqual(result["structure_only_auroc_oof"], 0.0)
        self.assertLessEqual(result["structure_only_auroc_oof"], 1.0)
        self.assertEqual(len(result["bootstrap_95_ci_gene_cluster"]), 2)
        self.assertEqual(result["bootstrap_iterations"]["valid"], 200)
        self.assertIn("gene-grouped", result["method"])

    def test_all_missing_feature_is_dropped_inside_each_training_fold(self):
        self.write_inputs(all_missing_ddg=True)
        rows = load_inputs(self.features_path, self.labels_path)
        result = evaluate(rows, folds=5, iterations=200, seed=42,
                          am_low_cutoff=0.3, structure_positive_cutoff=0.5)
        self.assertTrue(all(
            "monomer_ddg" in fold["dropped_all_missing_features"]
            for fold in result["cv_folds_detail"]
        ))
        self.assertEqual(result["feature_missingness_counts"]["monomer_ddg"], 20)

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

    def test_rejects_out_of_range_plddt(self):
        self.write_inputs()
        features = json.loads(self.features_path.read_text())
        features[0]["structural_features"]["plddt_confidence"] = 120
        self.features_path.write_text(json.dumps(features))
        with self.assertRaisesRegex(ValueError, "plddt_confidence must be in"):
            load_inputs(self.features_path, self.labels_path)

    def test_rejects_duplicate_gold_identity(self):
        self.write_inputs()
        with self.labels_path.open("a", newline="", encoding="utf-8") as handle:
            handle.write("GENE0,V00,B\n")
        with self.assertRaisesRegex(ValueError, "Duplicate gold label"):
            load_inputs(self.features_path, self.labels_path)

    def test_rejects_duplicate_feature_identity(self):
        self.write_inputs()
        features = json.loads(self.features_path.read_text())
        features.append(features[0])
        self.features_path.write_text(json.dumps(features))
        with self.assertRaisesRegex(ValueError, "Duplicate feature row"):
            load_inputs(self.features_path, self.labels_path)

    def test_cluster_bootstrap_resamples_gene_groups(self):
        labels = [0, 1, 0, 1, 0, 1]
        scores = [0.1, 0.9, 0.2, 0.8, 0.3, 0.7]
        genes = ["A", "A", "B", "B", "C", "C"]
        ci, meta = _cluster_bootstrap_auc(labels, scores, genes, 200, 7)
        self.assertEqual(meta["genes"], 3)
        self.assertEqual(meta["valid"], 200)
        self.assertEqual(len(ci), 2)


if __name__ == "__main__":
    unittest.main()
