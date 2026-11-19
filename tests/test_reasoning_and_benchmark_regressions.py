"""
Regression Test Suite for NeuroCapstone:
1. Reasoning import/API failure gracefully falls back without 500 or UnboundLocalError.
2. Empty inputs never yield fabricated pathogenic disease claims or invented metrics.
3. Invented PMIDs are removed from every output field (free text narrative, cited_pmids, experimental_highlights).
4. Benchmark `physics_only` actually invokes the real physics stage.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure project root is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

backend_dir = root_dir / "User Interface" / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from reasoning_engine import (
    _fallback_reasoning,
    validate_and_sanitize_reasoning,
    sanitize_narrative_pmids,
    generate_reasoning,
)


class TestReasoningAndBenchmarkRegressions(unittest.TestCase):

    def test_empty_inputs_never_yield_pathogenic_or_invented_claims(self):
        """Test 2: Empty inputs must return VUS/INSUFFICIENT_EVIDENCE, never invent diseases or metrics."""
        res = _fallback_reasoning(
            gene="TEST",
            variant="A1V",
            physics_data=None,
            context_data=None,
            evidence=[],
            status="NULL_RESULTS",
            source_note="Test Fallback",
        )

        structured = res["structured_data"]
        narrative = res["unstructured_verdict"]

        # 1. Verdict badge must be VUS or INSUFFICIENT_EVIDENCE
        self.assertEqual(structured["verdict_badge"], "VUS / INSUFFICIENT_EVIDENCE")
        self.assertIn("Insufficient", structured["confidence_assessment"])

        # 2. No fabricated disease claims (e.g. Parkinson, Lewy Body)
        diseases = [p["disease"].lower() for p in structured["clinical_phenotypes"]]
        self.assertFalse(any("parkinson" in d for d in diseases))
        self.assertFalse(any("lewy" in d for d in diseases))
        self.assertNotIn("parkinson", narrative.lower())
        self.assertNotIn("lewy", narrative.lower())

        # 3. Structural biophysics metrics must be marked Unavailable
        mech = structured["molecular_mechanism"]
        self.assertEqual(mech["affected_motif"], "Unavailable")
        self.assertIn("Unavailable", mech["key_disruption"])
        self.assertIn("unavailable", narrative.lower())

        # 4. Citations and highlights must be empty
        self.assertEqual(structured["cited_pmids"], [])
        self.assertEqual(structured["experimental_highlights"], [])

    def test_clinvar_exact_match_preserved_honestly(self):
        """Test 2b: ClinVar exact match is preserved and distinguished from model inference."""
        context_data = {
            "clinvar": {
                "variant_match": True,
                "clinical_significance": "Pathogenic",
                "conditions": ["Early-onset dystonia"],
            }
        }
        res = _fallback_reasoning(
            gene="DYT1",
            variant="GAG_del",
            physics_data=None,
            context_data=context_data,
            evidence=[],
            status="SUCCESS",
            source_note="Test Fallback",
        )

        structured = res["structured_data"]
        narrative = res["unstructured_verdict"]

        self.assertEqual(structured["verdict_badge"], "CLINVAR_PATHOGENIC")
        self.assertIn("ClinVar", structured["confidence_assessment"])
        self.assertTrue(any("Early-onset dystonia" in p["disease"] for p in structured["clinical_phenotypes"]))
        self.assertIn("Early-onset dystonia", narrative)

    def test_invented_pmids_removed_from_all_output_fields(self):
        """Test 3: Invented PMIDs are stripped from free-text narrative, cited_pmids, and highlights."""
        genuine_evidence = [
            {"pmid": "11111111", "title": "Real study 1", "text": "Finding 1"},
            {"pmid": "22222222", "title": "Real study 2", "text": "Finding 2"},
        ]

        # LLM output contains genuine (11111111) and invented (99999999, 88888888) PMIDs
        raw_narrative = (
            "Study [PMID: 11111111] found proteostasis deficits. "
            "Another study [PMID: 99999999] reported fabricated results. "
            "Also PMID: 88888888 claimed ungrounded effects."
        )
        raw_structured = {
            "cited_pmids": ["11111111", "99999999", "88888888"],
            "experimental_highlights": [
                {"system": "iPSC model", "finding": "Valid finding", "pmid": "11111111"},
                {"system": "Fabricated model", "finding": "Fake finding", "pmid": "99999999"},
            ],
        }

        sanitized_narrative, sanitized_structured = validate_and_sanitize_reasoning(
            raw_narrative, raw_structured, genuine_evidence
        )

        # 1. Free-text narrative: invented PMIDs are stripped
        self.assertIn("[PMID: 11111111]", sanitized_narrative)
        self.assertNotIn("99999999", sanitized_narrative)
        self.assertNotIn("88888888", sanitized_narrative)

        # 2. cited_pmids: only genuine PMIDs preserved
        self.assertEqual(sanitized_structured["cited_pmids"], ["11111111"])

        # 3. experimental_highlights: invalid PMID set to None
        highlights = sanitized_structured["experimental_highlights"]
        self.assertEqual(highlights[0]["pmid"], "11111111")
        self.assertIsNone(highlights[1]["pmid"])

    def test_api_reasoning_failure_gracefully_returns_response(self):
        """Test 1: If reasoning engine throws an exception, api handles it without UnboundLocalError / 500."""
        from fastapi.testclient import TestClient
        import api

        client = TestClient(api.app)

        # Mock run_pipeline to return immediately
        with patch("api.run_pipeline") as mock_pipe, \
             patch("reasoning_engine.generate_reasoning", side_effect=RuntimeError("Reasoning API exploded")):
            
            mock_pipe.return_value = (None, None, None)

            response = client.post("/analyze", json={"gene": "SNCA", "variant": "A53T"})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["gene"], "SNCA")
            self.assertEqual(data["variant"], "A53T")
            # Clinical narrative was populated by fallback builders despite reasoning failure
            self.assertIsNotNone(data["clinical_narrative"])
            self.assertGreater(len(data["clinical_narrative"]), 0)

    def test_benchmark_physics_only_invokes_physics_stage(self):
        """Test 4: Benchmark physics_only actually executes real physics without empty mock deltas."""
        from benchmark.benchmark import default_pipeline

        with patch("pipeline.run_pipeline") as mock_run_pipe, \
             patch("assemble_payload.run") as mock_assemble:

            mock_run_pipe.return_value = ("/fake/path.pdb", None, "/fake/analysis.json")
            mock_assemble.return_value = {"status": "SUCCESS", "physics_vector": {"deltas": {"delta_volume": 25.0}}}

            with patch("pathlib.Path.read_text", return_value='{"deltas": {"delta_volume": 25.0}}'):
                payload = default_pipeline("SNCA", "A53T", ablation="physics_only")

                # Verify run_pipeline was called with run_structure=True and run_analysis=True
                mock_run_pipe.assert_called_once()
                _, kwargs = mock_run_pipe.call_args
                self.assertTrue(kwargs.get("run_structure"))
                self.assertTrue(kwargs.get("run_analysis"))
                self.assertFalse(kwargs.get("run_context"))
                self.assertFalse(kwargs.get("run_fetch_literature"))


if __name__ == "__main__":
    unittest.main()
