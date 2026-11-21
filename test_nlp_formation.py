import unittest

from nlp_formation import (
    _build_mechanistic_keywords,
    create_nlp_query,
    extract_clinical_signals,
    extract_signals,
)


def _base_physics(**overrides):
    data = {
        "variant": "A53T",
        "comparison_view": {"residue": {"wt": "ALA", "mut": "THR"}},
        "deltas": {"delta_volume": 27.5, "delta_hydrophobicity": -2.5, "delta_charge": 0.0},
        "structural_context_wt": {
            "sasa": 51.54,
            "exposure": "Exposed",
            "secondary_structure": "Alpha Helix",
            "plddt_confidence": 89.62,
        },
        "stability_audit": {
            "salt_bridges_lost": [],
            "disulfides_lost": [],
            "h_bonds_lost_est": 0,
            "backbone_strain": "None",
        },
        "interface_contacts_lost": 0,
        "delta_aggregation": -0.0176,
    }
    data.update(overrides)
    return data


def _sample_clinical_context():
    return {
        "gene": "SNCA",
        "variant": "A53T",
        "clinvar": {
            "clinical_significance": "Pathogenic",
            "conditions": [
                "SNCA-related disorder",
                "Lewy body dementia",
                "Autosomal dominant Parkinson disease 1",
                "not provided",
                "Lewy body dementia",
            ],
        },
        "clingenreg": {
            "hgvs_used": "NP_000336.1:p.Ala53Thr",
        },
        "dbsnp": {
            "rsid": "rs104893877",
        },
        "alphamissense_sniper": {
            "score": 0.91,
            "verdict": "Pathogenic",
        },
        "gene_level_context": {
            "precision_layer_opentargets": {
                "top_diseases": [
                    {"disease": "Parkinson disease", "overall_score": 0.78},
                    {"disease": "Lewy body dementia", "overall_score": 0.74},
                ]
            },
            "recall_layer_ensembl": {
                "top_diseases": [
                    {"disease": "ClinVar: phenotype not specified", "count": 50},
                ]
            },
        },
    }


class TestNLPFormation(unittest.TestCase):
    def test_uses_biopython_site_and_clinical_context_without_verdict_leakage(self):
        query, hints = create_nlp_query(
            _base_physics(),
            clinical_context=_sample_clinical_context(),
            gene="SNCA",
        )
        self.assertIn("SNCA A53T (Ala53Thr, rs104893877)", query)
        self.assertIn("exposed alpha-helix", query)
        self.assertIn("Lewy body dementia", query)
        self.assertIn("Parkinson disease", query)
        self.assertNotIn("polymorphism", query.lower())
        self.assertNotIn("common variant", query.lower())
        self.assertNotIn("Pathogenic", query)
        self.assertNotIn("not provided", query.lower())
        self.assertNotIn("SNCA-related disorder", query)
        self.assertEqual(hints, ["A53T", "Ala53Thr", "p.Ala53Thr", "rs104893877"])

    def test_uses_biopython_3d_interactions(self):
        physics = _base_physics(
            variant="R143P",
            comparison_view={"residue": {"wt": "ARG", "mut": "PRO"}},
            structural_context_wt={
                "sasa": 4.2,
                "exposure": "Buried",
                "secondary_structure": "Alpha Helix",
                "plddt_confidence": 92.0,
            },
            stability_audit={
                "salt_bridges_lost": ["GLU46"],
                "disulfides_lost": ["CYS146"],
                "h_bonds_lost_est": 3,
                "backbone_strain": "Proline Helix Breaker",
            },
            interface_contacts_lost=2,
            delta_aggregation=0.12,
            monomer_ddg=1.6,
        )
        signals = extract_signals(physics)
        kws = [k for k, _ in _build_mechanistic_keywords(signals)]
        self.assertIn("monomer destabilization", kws)
        self.assertIn("disulfide bond disruption", kws)
        self.assertIn("salt bridge disruption", kws)
        self.assertIn("proline helix disruption", kws)
        self.assertIn("protein-protein interface disruption", kws)
        self.assertIn("hydrogen bond loss", kws)
        self.assertIn("aggregation propensity", kws)

        query, hints = create_nlp_query(physics, gene="SOD1")
        self.assertIn("buried alpha-helix", query)
        self.assertIn("monomer destabilization", query)
        self.assertIn("salt bridge disruption", query)
        self.assertEqual(hints, ["R143P", "Arg143Pro", "p.Arg143Pro"])

    def test_high_confidence_loop_is_not_labeled_low_confidence(self):
        physics = _base_physics(
            structural_context_wt={
                "sasa": 30.0,
                "exposure": "Partially Exposed",
                "secondary_structure": "Loop",
                "plddt_confidence": 91.0,
            }
        )
        query, _ = create_nlp_query(physics, gene="MAPT")
        self.assertIn("partially exposed loop region", query)
        self.assertNotIn("low-confidence", query)

    def test_neutral_fallback_avoids_polymorphism_bias(self):
        query, _ = create_nlp_query(_base_physics(), clinical_context=None, gene="SNCA")
        self.assertNotIn("polymorphism", query.lower())
        self.assertNotIn("common variant", query.lower())
        self.assertIn("functional impact and protein structure", query)

    def test_clinical_context_falls_back_to_opentargets_when_clinvar_missing(self):
        ctx = {
            "gene": "APP",
            "clinvar": None,
            "gene_level_context": {
                "precision_layer_opentargets": {
                    "top_diseases": [
                        {"disease": "Alzheimer disease", "overall_score": 0.81},
                        {"disease": "cerebral amyloid angiopathy, APP-related", "overall_score": 0.75},
                    ]
                }
            },
        }
        sig = extract_clinical_signals(ctx, gene="APP")
        self.assertEqual(
            sig["diseases"],
            ["Alzheimer disease", "cerebral amyloid angiopathy, APP-related"],
        )


if __name__ == "__main__":
    unittest.main()
