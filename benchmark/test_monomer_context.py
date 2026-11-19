import unittest
from pathlib import Path
from unittest.mock import patch

from assemble_payload import assemble_payload, build_vus_note, evaluate_physics_severity
from benchmark.thermompnn_s669 import predict_monomer_ddg, score_monomer_ddg
from nlp_formation import _build_mechanistic_keywords, extract_signals


def _physics(**extra):
    payload = {
        "variant": "A53T",
        "comparison_view": {"residue": {"wt": "ALA", "mut": "THR"}},
        "deltas": {"delta_volume": 0.0, "delta_hydrophobicity": 0.0, "delta_charge": 0.0},
        "structural_context_wt": {
            "exposure": "Exposed",
            "sasa": 50.0,
            "secondary_structure": "Loop",
            "plddt_confidence": 90.0,
        },
        "stability_audit": {"h_bonds_lost_est": 0},
    }
    payload.update(extra)
    return payload


class MonomerContextTests(unittest.TestCase):
    def test_a_destabilizing_score_enters_the_literature_query(self):
        signals = extract_signals(_physics(monomer_ddg=1.5))
        keywords = [phrase for phrase, _category in _build_mechanistic_keywords(signals)]
        self.assertIn("monomer destabilization", keywords)

    def test_a_large_table_delta_is_not_a_severe_result(self):
        physics = _physics(deltas={"delta_volume": 80.0, "delta_hydrophobicity": -4.0, "delta_charge": -1.0})
        severe, violations, count = evaluate_physics_severity(physics)
        self.assertFalse(severe)
        self.assertEqual(violations, [])
        self.assertEqual(count, 0)
        keywords = [phrase for phrase, _category in _build_mechanistic_keywords(extract_signals(physics))]
        self.assertNotIn("steric hindrance", keywords)
        self.assertNotIn("protein destabilization", keywords)
        self.assertNotIn("amyloid formation", keywords)

    def test_thermompnn_at_least_one_kcal_is_the_severe_result(self):
        severe, violations, count = evaluate_physics_severity(_physics(monomer_ddg=1.5))
        self.assertTrue(severe)
        self.assertEqual(count, 1)
        self.assertIn("+1.50", violations[0])

    def test_a_small_or_missing_score_stays_out_of_the_query(self):
        small = [phrase for phrase, _category in _build_mechanistic_keywords(extract_signals(_physics(monomer_ddg=0.4)))]
        missing = [phrase for phrase, _category in _build_mechanistic_keywords(extract_signals(_physics()))]
        self.assertNotIn("monomer destabilization", small)
        self.assertNotIn("monomer destabilization", missing)

    def test_the_verdict_note_states_the_monomer_score(self):
        note = build_vus_note(_physics(monomer_ddg=1.5), ["volume change"])
        self.assertIn("ThermoMPNN predicts a monomer folding ΔΔG of +1.50 kcal/mol", note)
        silent = build_vus_note(_physics(), ["volume change"])
        self.assertNotIn("ThermoMPNN", silent)

    def test_missing_weights_do_not_invent_a_score(self):
        self.assertIsNone(predict_monomer_ddg("missing.pdb", "A53T", "A"))

    def test_missing_dependency_is_recorded_not_swallowed(self):
        pdb = Path("data/benchmarks/s669_structures/1DIV.pdb")
        with patch("benchmark.thermompnn_s669.load_thermompnn", side_effect=ModuleNotFoundError("No module named 'omegaconf'")):
            res = score_monomer_ddg(pdb, "D23A", "A")
        self.assertIsNone(res["monomer_ddg"])
        self.assertEqual(res["status"], "missing_dependency")
        self.assertIn("omegaconf", res["error"])

    def test_residue_mismatch_is_recorded_not_swallowed(self):
        pdb = Path("data/benchmarks/s669_structures/1DIV.pdb")
        if not pdb.is_file():
            self.skipTest("1DIV.pdb not present")
        res = score_monomer_ddg(pdb, "W999A", "A")
        self.assertIsNone(res["monomer_ddg"])
        self.assertEqual(res["status"], "residue_mismatch")
        self.assertIn("residue_mismatch", res["error"])

    def test_real_pdb_scores_without_omegaconf(self):
        import torch

        pdb = Path("data/benchmarks/s669_structures/1DIV.pdb")
        if not pdb.is_file():
            self.skipTest("1DIV.pdb not present")
        original_load = torch.load
        res = score_monomer_ddg(pdb, "D23A", "A")
        self.assertIs(torch.load, original_load)
        self.assertEqual(res["status"], "scored")
        self.assertIsInstance(res["monomer_ddg"], float)
        self.assertIsNone(res["error"])

    def test_payload_records_missing_thermompnn_status_without_treating_as_scored(self):
        physics = _physics(
            thermompnn_status="missing_dependency",
            thermompnn_error="ModuleNotFoundError: No module named 'omegaconf'",
        )
        payload = assemble_payload(query="SNCA A53T", ranked_results=[], physics_vector=physics)
        self.assertEqual(payload["confidence_matrix"]["thermompnn_status"], "MISSING_DEPENDENCY")
        self.assertEqual(payload["thermompnn"]["status"], "missing_dependency")
        self.assertIsNone(payload["thermompnn"]["monomer_ddg"])
        self.assertIn("omegaconf", payload["thermompnn"]["error"])
        self.assertEqual(payload["status"], "LOW_CONFIDENCE")


if __name__ == "__main__":
    unittest.main()
