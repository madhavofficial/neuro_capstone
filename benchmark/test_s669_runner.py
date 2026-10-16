import tempfile
import unittest
from pathlib import Path

from benchmark.thermompnn_s669 import resolve_sequence_index
from benchmark.s669_runner import (
    collapse_stability_score,
    correlation_meets_simple_predictors,
    load_variants,
    pearson,
    same_amino_acid,
    spearman,
)


def _analysis(**overrides):
    analysis = {
        "deltas": {"delta_volume": 0.0, "delta_hydrophobicity": 0.0, "delta_charge": 0.0},
        "structural_context_wt": {
            "sasa": 0.0,
            "exposure": "Buried",
            "secondary_structure": "Alpha Helix",
            "plddt_confidence": 90.0,
        },
        "stability_audit": {
            "salt_bridges_lost": [],
            "salt_bridges_gained": [],
            "disulfides_lost": [],
            "disulfides_gained": [],
            "h_bonds_lost_est": 0,
            "h_bonds_gained_est": 0,
            "backbone_strain": "None",
        },
        "wild_type": {"charge": 0.0},
        "mutant_properties": {"charge": 0.0},
    }
    for key, value in overrides.items():
        analysis[key] = value
    return analysis


class S669RunnerTests(unittest.TestCase):
    def test_same_amino_acid_accepts_histidine_protonation(self):
        self.assertTrue(same_amino_acid("HSD", "H"))
        self.assertTrue(same_amino_acid("MSE", "M"))
        self.assertFalse(same_amino_acid("ALA", "S"))

    def test_collapse_treats_core_volume_and_lost_contacts_as_destabilizing(self):
        quiet = collapse_stability_score(_analysis())
        bulky = collapse_stability_score(
            _analysis(deltas={"delta_volume": 60.0, "delta_hydrophobicity": 0.0, "delta_charge": 0.0})
        )
        polar_core = collapse_stability_score(
            _analysis(deltas={"delta_volume": 0.0, "delta_hydrophobicity": -4.5, "delta_charge": 0.0})
        )
        broken = _analysis()
        broken["stability_audit"]["salt_bridges_lost"] = ["ASP10"]
        broken["stability_audit"]["h_bonds_lost_est"] = 2
        self.assertGreater(bulky, quiet)
        self.assertGreater(polar_core, quiet)
        self.assertAlmostEqual(collapse_stability_score(broken) - quiet, 3.0)

    def test_guessed_gained_contacts_do_not_change_the_score(self):
        quiet = collapse_stability_score(_analysis())
        guessed = _analysis()
        guessed["stability_audit"]["h_bonds_gained_est"] = 20
        guessed["stability_audit"]["salt_bridges_gained"] = ["LYS10", "ARG20"]
        guessed["stability_audit"]["disulfides_gained"] = ["CYS30"]
        self.assertEqual(collapse_stability_score(guessed), quiet)

    def test_surface_site_weighs_packing_less_than_a_buried_helix(self):
        buried = collapse_stability_score(
            _analysis(deltas={"delta_volume": 60.0, "delta_hydrophobicity": 0.0, "delta_charge": 0.0})
        )
        exposed = _analysis(
            deltas={"delta_volume": 60.0, "delta_hydrophobicity": 0.0, "delta_charge": 0.0},
            structural_context_wt={
                "sasa": 80.0,
                "exposure": "Exposed",
                "secondary_structure": "Loop",
                "plddt_confidence": 40.0,
            },
        )
        self.assertGreater(buried, collapse_stability_score(exposed))

    def test_rank_and_linear_correlation(self):
        self.assertAlmostEqual(pearson([1, 2, 3, 4], [2, 4, 6, 8]), 1.0)
        self.assertAlmostEqual(spearman([1, 2, 3, 4], [1, 2, 4, 8]), 1.0)
        self.assertAlmostEqual(spearman([1, 1, 2], [1, 1, 3]), 1.0)

    def test_name_decision_uses_the_published_floor(self):
        self.assertTrue(correlation_meets_simple_predictors(0.22))
        self.assertFalse(correlation_meets_simple_predictors(0.21))
        self.assertFalse(correlation_meets_simple_predictors(float("nan")))

    def test_thermompnn_index_uses_residue_number_then_gaps(self):
        self.assertEqual(resolve_sequence_index("ACD", ["10", "11", "12"], 11, "C"), 1)
        self.assertEqual(resolve_sequence_index("-ACD", ["10", "11", "12"], 10, "A"), 1)
        self.assertIsNone(resolve_sequence_index("ACD", ["10", "11", "12"], 11, "A"))

    def test_variant_table_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "s669.csv"
            path.write_text("pdb,chain,wt,position,mut,ddg\n1A0F,A,S,11,A,-1.8\n", encoding="utf-8")
            rows = load_variants(path)
        self.assertEqual(rows[0]["pdb"], "1A0F")
        self.assertEqual(rows[0]["position"], 11)
        self.assertEqual(rows[0]["ddg"], -1.8)


if __name__ == "__main__":
    unittest.main()
