import unittest

from assemble_payload import build_vus_note
from benchmark.thermompnn_s669 import predict_monomer_ddg
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


if __name__ == "__main__":
    unittest.main()
