import csv
import json
import tempfile
import unittest
from pathlib import Path

from benchmark.batch_feature_export import export_batch


class BatchFeatureExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.runs = self.root / "runs"
        run = self.runs / "run-001"
        (run / "analysis").mkdir(parents=True)
        self.analysis = {
            "structural_context_wt": {"exposure": "Buried", "sasa": 22.0,
                "secondary_structure": "Helix", "plddt_confidence": 90.0},
            "deltas": {"delta_volume": 1.0, "delta_hydrophobicity": -0.2, "delta_charge": 0.0},
            "stability_audit": {"backbone_strain": "None", "salt_bridges_lost": [],
                "disulfides_lost": [], "h_bonds_lost_est": 0},
            "interface_contacts_lost": 0, "delta_aggregation": 0.1, "monomer_ddg": None,
        }
        (run / "analysis" / "TTR_V50M_physics.json").write_text(json.dumps(self.analysis))
        (run / "payload.json").write_text(json.dumps({
            "clinical_context": {"alphamissense_sniper": {"score": 0.22},
                                 "clinvar": {"clinical_significance": "Pathogenic"}}
        }))
        self.labels = self.root / "labels.csv"
        with self.labels.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["gene", "variant", "label"])
            w.writeheader()
            w.writerow({"gene": "TTR", "variant": "V50M", "label": "LP"})
            w.writerow({"gene": "SNCA", "variant": "A53T", "label": "P"})

    def test_exports_feature_json_and_separate_label_audit(self):
        features = self.root / "features.json"
        audit = self.root / "audit.csv"
        result = export_batch(self.runs, self.labels, features, audit)
        rows = json.loads(features.read_text())
        self.assertEqual(result["feature_rows_exported"], 1)
        self.assertEqual(rows[0]["alphamissense_score"], 0.22)
        encoded = json.dumps(rows).lower()
        self.assertNotIn("clinvar", encoded)
        self.assertNotIn("pathogenic", encoded)
        with audit.open(newline="", encoding="utf-8") as handle:
            audit_rows = list(csv.DictReader(handle))
        audit_by_key = {(row["gene"], row["variant"]): row for row in audit_rows}
        self.assertEqual(audit_by_key[("TTR", "V50M")]["label"], "LP")
        self.assertEqual(audit_by_key[("SNCA", "A53T")]["status"], "missing_physics")

    def test_requires_alpha_missense_when_requested(self):
        run = self.runs / "run-001"
        (run / "payload.json").write_text(json.dumps({"clinical_context": {}}))
        features = self.root / "features.json"
        audit = self.root / "audit.csv"
        result = export_batch(self.runs, self.labels, features, audit, require_alphamissense=True)
        self.assertEqual(result["feature_rows_exported"], 0)
        self.assertEqual(result["missing_alphamissense"], 1)


if __name__ == "__main__":
    unittest.main()
