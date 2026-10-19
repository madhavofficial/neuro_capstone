import json
import tempfile
import unittest
from pathlib import Path

from benchmark.feature_vector import (
    GUESSED_GAIN_KEYS,
    STRUCTURAL_FEATURE_KEYS,
    build_feature_row,
)


# One alanine at residue 53. Enough for a virtual A53T substitution.
_ALANINE_53 = """\
ATOM      1  N   ALA A  53      11.104  13.207   2.000  1.00 90.00           N
ATOM      2  CA  ALA A  53      12.560  13.207   2.000  1.00 90.00           C
ATOM      3  C   ALA A  53      13.000  14.640   2.000  1.00 90.00           C
ATOM      4  O   ALA A  53      12.500  15.500   2.700  1.00 90.00           O
ATOM      5  CB  ALA A  53      13.000  12.500   3.200  1.00 90.00           C
END
"""


def _keys(value):
    found = set()
    if isinstance(value, dict):
        found.update(value)
        for item in value.values():
            found.update(_keys(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_keys(item))
    return found


class FeatureVectorTests(unittest.TestCase):
    def test_row_keeps_measured_features_and_drops_clinvar_and_guessed_gains(self):
        analysis = {
            "structural_context_wt": {
                "sasa": 51.54,
                "exposure": "Exposed",
                "secondary_structure": "Unknown",
                "plddt_confidence": 89.62,
            },
            "deltas": {
                "delta_volume": 27.5,
                "delta_hydrophobicity": -2.5,
                "delta_charge": 0.0,
            },
            "stability_audit": {
                "salt_bridges_lost": [],
                "salt_bridges_gained": ["LYS10"],
                "disulfides_lost": [],
                "disulfides_gained": ["CYS30"],
                "h_bonds_lost_est": 0,
                "h_bonds_gained_est": 4,
                "backbone_strain": "None",
            },
            "comparison_view": {
                "sasa": {"wt": 51.54, "mut": None, "delta": None},
            },
        }
        context = {
            "alphamissense_sniper": {"score": 0.34, "verdict": "Benign"},
            "clinvar": {"clinical_significance": "Pathogenic"},
            "clinical_label": "Pathogenic",
        }

        row = build_feature_row("SNCA", "A53T", analysis, context)
        encoded = json.dumps(row)

        self.assertEqual(row["alphamissense_score"], 0.34)
        self.assertEqual(set(row["structural_features"]), set(STRUCTURAL_FEATURE_KEYS))
        self.assertEqual(row["structural_features"]["delta_volume"], 27.5)
        self.assertEqual(row["structural_features"]["delta_hydrophobicity"], -2.5)
        self.assertEqual(row["structural_features"]["exposure"], "Exposed")
        self.assertFalse(_keys(row) & set(GUESSED_GAIN_KEYS))
        self.assertNotIn("clinvar", encoded.lower())
        self.assertNotIn("clinical_label", encoded)
        self.assertNotIn("clinical_significance", encoded)
        self.assertNotIn("Pathogenic", encoded)

    def test_missing_context_leaves_the_score_empty(self):
        analysis = {
            "structural_context_wt": {
                "sasa": 1.0,
                "exposure": "Buried",
                "secondary_structure": "Alpha Helix",
                "plddt_confidence": 95.0,
            },
            "deltas": {
                "delta_volume": 0.0,
                "delta_hydrophobicity": 0.0,
                "delta_charge": 0.0,
            },
            "stability_audit": {
                "salt_bridges_lost": ["ASP10"],
                "disulfides_lost": [],
                "h_bonds_lost_est": 2,
                "backbone_strain": "None",
            },
        }
        row = build_feature_row("TTR", "V50M", analysis, None)
        self.assertIsNone(row["alphamissense_score"])
        self.assertEqual(row["structural_features"]["salt_bridges_lost"], ["ASP10"])
        self.assertEqual(row["structural_features"]["h_bonds_lost_est"], 2)

    def test_virtual_substitution_on_a_wild_type_file(self):
        from analyze_structure import analyze_protein

        with tempfile.TemporaryDirectory() as tmp:
            pdb = Path(tmp) / "ala53.pdb"
            pdb.write_text(_ALANINE_53)
            analysis = analyze_protein(str(pdb), "A53T", chain_id="A", verbose=False)

        self.assertIsNotNone(analysis)
        row = build_feature_row("SNCA", "A53T", analysis, None)
        features = row["structural_features"]
        self.assertEqual(features["delta_volume"], 27.5)
        self.assertEqual(features["delta_hydrophobicity"], -2.5)
        self.assertEqual(features["delta_charge"], 0.0)
        self.assertIsNotNone(features["sasa"])
        self.assertIsNotNone(features["exposure"])
        self.assertNotIn("mut", features)


if __name__ == "__main__":
    unittest.main()
