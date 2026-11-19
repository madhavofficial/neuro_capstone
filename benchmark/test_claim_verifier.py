import tempfile
import unittest
from pathlib import Path

from benchmark.benchmark import calculate_metrics
from benchmark.claim_verifier import verify_claim
from benchmark.full_runner import FULL_PIPELINE_STAGES, _check_synthesis, write_markdown_report


def _sample_payload():
    return {
        "status": "SUCCESS",
        "evidence": [
            {"pmid": "41002401", "title": "SNCA A53T organoids", "text": "SNCA A53T causes aggregation."},
        ],
        "clinical_context": {
            "clinvar": {
                "accession": "VCV000014007.42",
                "variation_id": "14007",
                "clinical_significance": "Pathogenic",
            },
            "alphamissense_sniper": {
                "score": 0.7863,
                "verdict": "Pathogenic",
            },
            "dbsnp": {
                "rsid": "rs104893877",
                "dbsnp_data": {
                    "rsid": "rs104893877",
                    "citations": [31270413],
                    "alleles": [
                        {"allele": "G", "freq": {"gnomad": 0.9999}},
                        {"allele": "A", "freq": {"gnomad": 0.0001, "korea1k": 0.05}},
                    ],
                },
            },
            "gene_level_context": {
                "precision_layer_opentargets": {
                    "top_diseases": [{"disease": "Parkinson disease", "score": 0.91}],
                },
                "recall_layer_ensembl": {
                    "top_diseases": [{"disease": "Lewy body dementia", "count": 65}],
                },
            },
        },
    }


TARGET = {"gene": "SNCA", "variant": "A53T"}


class ClaimVerifierTests(unittest.TestCase):
    def test_paper_citation_valid_only_when_pmid_in_evidence(self):
        payload = _sample_payload()
        ok = verify_claim({"text": "SNCA A53T organoids aggregate.", "pmid": "41002401"}, payload, TARGET)
        self.assertEqual(ok["claim_category"], "paper_citation")
        self.assertTrue(ok["citation_valid"])
        self.assertFalse(ok["unsupported"])

        invented = verify_claim({"text": "SNCA A53T fabricated study.", "pmid": "99999999"}, payload, TARGET)
        self.assertEqual(invented["claim_category"], "paper_citation")
        self.assertFalse(invented["citation_valid"])
        self.assertTrue(invented["unsupported"])

        # dbSNP citation PMID not in payload["evidence"] stays unverified.
        dbsnp_pmid = verify_claim({"text": "SNCA A53T gnomAD paper.", "pmid": "31270413"}, payload, TARGET)
        self.assertEqual(dbsnp_pmid["claim_category"], "paper_citation")
        self.assertFalse(dbsnp_pmid["citation_valid"])
        self.assertTrue(dbsnp_pmid["unsupported"])

        # ClinVar variation ID placed in pmid field is still an invalid paper citation.
        clinvar_as_pmid = verify_claim({"text": "ClinVar lists SNCA A53T (14007) as Pathogenic.", "pmid": "14007"}, payload, TARGET)
        self.assertEqual(clinvar_as_pmid["claim_category"], "paper_citation")
        self.assertFalse(clinvar_as_pmid["citation_valid"])
        self.assertTrue(clinvar_as_pmid["unsupported"])

    def test_clinvar_claim_requires_matching_id_and_class(self):
        payload = _sample_payload()
        ok_vid = verify_claim(
            {"text": "ClinVar lists SNCA A53T (variation ID 14007) as Pathogenic.", "pmid": None},
            payload,
            TARGET,
        )
        self.assertEqual(ok_vid["claim_category"], "clinical_database")
        self.assertTrue(ok_vid["clinical_field_valid"])
        self.assertFalse(ok_vid["unsupported"])

        ok_acc = verify_claim(
            {"text": "ClinVar VCV000014007.42 classifies SNCA A53T as Pathogenic.", "pmid": "null"},
            payload,
            TARGET,
        )
        self.assertTrue(ok_acc["clinical_field_valid"])
        self.assertFalse(ok_acc["unsupported"])

        wrong_class = verify_claim(
            {"text": "ClinVar lists SNCA A53T (variation ID 14007) as Benign.", "pmid": None},
            payload,
            TARGET,
        )
        self.assertEqual(wrong_class["claim_category"], "clinical_database")
        self.assertFalse(wrong_class["clinical_field_valid"])
        self.assertTrue(wrong_class["unsupported"])

        missing_id = verify_claim(
            {"text": "ClinVar says SNCA A53T is Pathogenic.", "pmid": None},
            payload,
            TARGET,
        )
        self.assertFalse(missing_id["clinical_field_valid"])
        self.assertTrue(missing_id["unsupported"])

        wrong_id = verify_claim(
            {"text": "ClinVar lists SNCA A53T (VCV000099999.1) as Pathogenic.", "pmid": None},
            payload,
            TARGET,
        )
        self.assertFalse(wrong_id["clinical_field_valid"])
        self.assertTrue(wrong_id["unsupported"])

        # "Likely pathogenic" must not silently match a "Pathogenic" ClinVar record.
        tier_mismatch = verify_claim(
            {"text": "ClinVar lists SNCA A53T (variation ID 14007) as Likely pathogenic.", "pmid": None},
            payload,
            TARGET,
        )
        self.assertFalse(tier_mismatch["clinical_field_valid"])
        self.assertTrue(tier_mismatch["unsupported"])

    def test_real_pmid_cannot_hide_false_clinvar_claim(self):
        payload = _sample_payload()
        mixed = verify_claim(
            {"text": "ClinVar lists SNCA A53T (variation ID 14007) as Benign.", "pmid": "41002401"},
            payload,
            TARGET,
        )
        self.assertEqual(mixed["claim_category"], "paper_citation")
        self.assertTrue(mixed["citation_valid"])
        self.assertFalse(mixed["clinical_field_valid"])
        self.assertTrue(mixed["unsupported"])

        mixed_freq = verify_claim(
            {"text": "SNCA A53T has a gnomAD allele frequency of 0.42.", "pmid": "41002401"},
            payload,
            TARGET,
        )
        self.assertTrue(mixed_freq["citation_valid"])
        self.assertFalse(mixed_freq["clinical_field_valid"])
        self.assertTrue(mixed_freq["unsupported"])

        payload_no_dbsnp = _sample_payload()
        del payload_no_dbsnp["clinical_context"]["dbsnp"]
        mixed_freq_missing_dbsnp = verify_claim(
            {"text": "SNCA A53T has a gnomAD allele frequency of 0.05.", "pmid": "41002401"},
            payload_no_dbsnp,
            TARGET,
        )
        self.assertTrue(mixed_freq_missing_dbsnp["citation_valid"])
        self.assertFalse(mixed_freq_missing_dbsnp["clinical_field_valid"])
        self.assertTrue(mixed_freq_missing_dbsnp["unsupported"])

        # Mentioning gnomAD in a cited paper without stating a frequency or rsID stays a pure paper citation.
        paper_mentions_gnomad = verify_claim(
            {"text": "This SNCA A53T paper discusses gnomAD methodology.", "pmid": "41002401"},
            payload_no_dbsnp,
            TARGET,
        )
        self.assertTrue(paper_mentions_gnomad["citation_valid"])
        self.assertIsNone(paper_mentions_gnomad["clinical_field_valid"])
        self.assertFalse(paper_mentions_gnomad["unsupported"])

        am_tier_mismatch = verify_claim(
            {"text": "AlphaMissense assigns SNCA A53T a score of 0.7863 with verdict Likely pathogenic.", "pmid": None},
            payload,
            TARGET,
        )
        self.assertFalse(am_tier_mismatch["clinical_field_valid"])
        self.assertTrue(am_tier_mismatch["unsupported"])

    def test_unmatched_open_targets_claim_counts_as_unsupported(self):
        payload = _sample_payload()
        bad_gc = verify_claim(
            {"text": "Open Targets associates SNCA with Cystic fibrosis.", "pmid": None, "claim_type": "gene_context"},
            payload,
            TARGET,
        )
        self.assertEqual(bad_gc["claim_category"], "gene_context")
        self.assertFalse(bad_gc["gene_context_valid"])
        self.assertTrue(bad_gc["unsupported"])
        metrics = calculate_metrics([{"completed": True, "gold_label": "pathogenic", "prediction": "pathogenic", "claim_checks": [bad_gc], "json_schema_valid": True, "runtime_seconds": 1.0}])
        self.assertEqual(metrics["unsupported_claim_rate"], 1.0)

    def test_alphamissense_claim_requires_matching_score_and_verdict(self):
        payload = _sample_payload()
        ok = verify_claim(
            {"text": "AlphaMissense assigns SNCA A53T a score of 0.7863 with verdict Pathogenic.", "pmid": None},
            payload,
            TARGET,
        )
        self.assertEqual(ok["claim_category"], "clinical_database")
        self.assertTrue(ok["clinical_field_valid"])
        self.assertFalse(ok["unsupported"])

        wrong_score = verify_claim(
            {"text": "AlphaMissense assigns SNCA A53T a score of 0.1234 with verdict Pathogenic.", "pmid": None},
            payload,
            TARGET,
        )
        self.assertFalse(wrong_score["clinical_field_valid"])
        self.assertTrue(wrong_score["unsupported"])

        wrong_verdict = verify_claim(
            {"text": "AlphaMissense assigns SNCA A53T a score of 0.7863 with verdict Benign.", "pmid": None},
            payload,
            TARGET,
        )
        self.assertFalse(wrong_verdict["clinical_field_valid"])
        self.assertTrue(wrong_verdict["unsupported"])

        name_only = verify_claim(
            {"text": "AlphaMissense evaluated SNCA A53T.", "pmid": None},
            payload,
            TARGET,
        )
        self.assertFalse(name_only["clinical_field_valid"])
        self.assertTrue(name_only["unsupported"])

    def test_dbsnp_rsid_and_frequency_claims(self):
        payload = _sample_payload()
        ok_rsid = verify_claim(
            {"text": "dbSNP records SNCA A53T under rs104893877.", "pmid": None},
            payload,
            TARGET,
        )
        self.assertEqual(ok_rsid["claim_category"], "clinical_database")
        self.assertTrue(ok_rsid["clinical_field_valid"])
        self.assertFalse(ok_rsid["unsupported"])

        ok_freq_pct = verify_claim(
            {"text": "The A allele frequency for SNCA A53T (rs104893877) is ~5% in population data.", "pmid": None},
            payload,
            TARGET,
        )
        self.assertTrue(ok_freq_pct["clinical_field_valid"])
        self.assertFalse(ok_freq_pct["unsupported"])

        wrong_rsid = verify_claim(
            {"text": "dbSNP records SNCA A53T under rs9999999.", "pmid": None},
            payload,
            TARGET,
        )
        self.assertFalse(wrong_rsid["clinical_field_valid"])
        self.assertTrue(wrong_rsid["unsupported"])

        wrong_freq = verify_claim(
            {"text": "The minor allele frequency for SNCA A53T is 0.42 in gnomAD.", "pmid": None},
            payload,
            TARGET,
        )
        self.assertFalse(wrong_freq["clinical_field_valid"])
        self.assertTrue(wrong_freq["unsupported"])

    def test_gene_level_open_targets_marked_as_gene_context_not_variant_evidence(self):
        payload = _sample_payload()
        gc = verify_claim(
            {"text": "Open Targets associates SNCA with Parkinson disease.", "pmid": None, "claim_type": "gene_context"},
            payload,
            TARGET,
        )
        self.assertEqual(gc["claim_category"], "gene_context")
        self.assertTrue(gc["gene_context"])
        self.assertFalse(gc["variant_level_evidence"])
        self.assertTrue(gc["gene_context_valid"])
        self.assertIsNone(gc["citation_valid"])
        self.assertIsNone(gc["clinical_field_valid"])

    def test_metrics_and_report_split_paper_citation_from_clinical_field_validity(self):
        payload = _sample_payload()
        synthesis = {
            "prediction": "pathogenic",
            "conclusion": "Pathogenic based on supplied evidence.",
            "uncertainty": False,
            "scope": "variant",
            "claims": [
                {"text": "SNCA A53T organoids aggregate.", "pmid": "41002401", "claim_type": "functional"},
                {"text": "SNCA A53T invented paper.", "pmid": "99999999", "claim_type": "functional"},
                {"text": "ClinVar lists SNCA A53T (variation ID 14007) as Pathogenic.", "pmid": None, "claim_type": "clinical"},
                {"text": "AlphaMissense assigns SNCA A53T a score of 0.7863 with verdict Pathogenic.", "pmid": None, "claim_type": "computational"},
                {"text": "dbSNP records SNCA A53T under rs104893877.", "pmid": None, "claim_type": "population"},
                {"text": "Open Targets associates SNCA with Parkinson disease.", "pmid": None, "claim_type": "gene_context"},
            ],
        }
        valid, checks, _unc, _scope = _check_synthesis(synthesis, payload, TARGET)
        self.assertTrue(valid)

        row = {
            "run_id": "r1",
            "variant_id": "snca-a53t",
            "gene": "SNCA",
            "variant": "A53T",
            "ablation": "all_evidence",
            "model": "GPT-OSS 120B",
            "completed": True,
            "gold_label": "pathogenic",
            "prediction": "pathogenic",
            "json_schema_valid": True,
            "claim_checks": checks,
            "top5_evidence_count": 1,
            "top5_variant_mentions": 1,
            "runtime_seconds": 1.0,
            "stage_status": {stage: "success" for stage in FULL_PIPELINE_STAGES},
            "model_meta": {"provider": "groq", "model": "openai/gpt-oss-120b", "mode": "api"},
        }
        metrics = calculate_metrics([row])
        # Paper-citation validity is 1/2 = 0.5 (invented PMID is NOT hidden by 3/3 clinical claims!)
        self.assertEqual(metrics["paper_citation_validity"], 0.5)
        self.assertEqual(metrics["invented_pmid_rate"], 0.5)
        self.assertEqual(metrics["clinical_field_validity"], 1.0)
        self.assertEqual(metrics["n_paper_citation_claims"], 2)
        self.assertEqual(metrics["n_clinical_database_claims"], 3)
        self.assertEqual(metrics["n_gene_context_claims"], 1)

        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.md"
            write_markdown_report([row], report_path)
            md = report_path.read_text(encoding="utf-8")
            self.assertIn("| paper_citation_validity | 0.5 |", md)
            self.assertIn("| invented_pmid_rate | 0.5 |", md)
            self.assertIn("| clinical_field_validity | 1.0 |", md)
            self.assertIn("| n_gene_context_claims | 1 |", md)


if __name__ == "__main__":
    unittest.main()
