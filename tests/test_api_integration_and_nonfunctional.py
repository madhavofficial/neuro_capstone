import concurrent.futures
import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_PATH = PROJECT_ROOT / "User Interface" / "backend" / "api.py"


def _load_api_module():
    spec = importlib.util.spec_from_file_location("neuro_capstone_ui_api", API_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


api_module = _load_api_module()


class TestAPIIntegration(unittest.TestCase):
    """Functional & integration tests for the FastAPI backend adapter."""

    def setUp(self):
        self.client = TestClient(api_module.app)

    def test_health_endpoint_returns_ok(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["backend"], "active")
        self.assertTrue(os.path.isdir(body["project_root"]))

    def test_analyze_rejects_empty_and_missing_fields(self):
        # Missing fields -> Pydantic 422
        resp_missing = self.client.post("/analyze", json={})
        self.assertEqual(resp_missing.status_code, 422)

        # Empty strings -> Pydantic min_length=1 -> 422
        resp_empty = self.client.post("/analyze", json={"gene": "", "variant": "A53T"})
        self.assertEqual(resp_empty.status_code, 422)

        # Whitespace-only -> explicit 400 Bad Request
        resp_ws = self.client.post("/analyze", json={"gene": "   ", "variant": "A53T"})
        self.assertEqual(resp_ws.status_code, 400)
        self.assertIn("required", resp_ws.json()["detail"].lower())

    def test_analyze_happy_path_and_top5_evidence_cap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pdb_file = Path(tmpdir) / "SNCA.pdb"
            pdb_file.write_text("ATOM      1  CA  ALA A  53       1.000   2.000   3.000\n", encoding="utf-8")

            physics_file = Path(tmpdir) / "SNCA_A53T_physics.json"
            physics_file.write_text(
                json.dumps({"deltas": {"delta_volume": 27.5, "delta_hydrophobicity": -2.5}}),
                encoding="utf-8",
            )

            mock_context = {
                "clinvar": {"clinical_significance": "Pathogenic", "variation_id": "14010"}
            }
            mock_evidence = [
                {
                    "text": f"Paper {i} discussing SNCA A53T",
                    "pmid": str(10000000 + i),
                    "title": f"Study {i}",
                    "score": 0.9 - i * 0.05,
                    "score_type": "raw_cross_encoder_score",
                }
                for i in range(7)
            ]
            mock_payload = {
                "status": "SUCCESS",
                "confidence_matrix": {
                    "physics_engine": "HEURISTIC",
                    "literature_rag": "SUCCESS",
                    "clinical_context": "HIGH",
                },
                "evidence": mock_evidence,
            }
            mock_reasoning = {
                "unstructured_verdict": (
                    "Supported by [PMID: 10000000] and unverified [PMID: 99999999]."
                ),
                "structured_data": {
                    "verdict_badge": "PATHOGENIC",
                    "summary": "See PMID 10000001 and PMID 88888888.",
                },
                "model_used": "test-model",
            }

            with patch.object(
                api_module,
                "run_pipeline",
                return_value=(str(pdb_file), mock_context, str(physics_file)),
            ), patch.object(
                api_module,
                "run_full_pipeline",
                return_value=mock_payload,
            ), patch(
                "reasoning_engine.generate_reasoning",
                return_value=mock_reasoning,
            ):
                resp = self.client.post("/analyze", json={"gene": " SNCA ", "variant": " A53T "})

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["gene"], "SNCA")
        self.assertEqual(data["variant"], "A53T")
        self.assertEqual(data["status"], "SUCCESS")
        self.assertEqual(len(data["evidence"]), 5)  # capped at top 5
        self.assertIn("ATOM", data["pdb_content"])
        self.assertEqual(data["physics_data"]["deltas"]["delta_volume"], 27.5)
        self.assertEqual(data["reasoning_model"], "test-model")
        self.assertIsNone(data["warnings"])

        # Hallucination guardrail: retrieved PMIDs preserved, unretrieved PMIDs flagged
        self.assertIn("[PMID: 10000000]", data["clinical_narrative"])
        self.assertIn("[Unverified PMID: 99999999]", data["clinical_narrative"])
        self.assertIn("PMID 10000001", data["structured_reasoning"]["summary"])
        self.assertIn("Unverified PMID 88888888", data["structured_reasoning"]["summary"])

    def test_analyze_graceful_degradation_on_downstream_failures(self):
        with patch.object(
            api_module,
            "run_pipeline",
            return_value=("/nonexistent/SNCA.pdb", {"clinvar": {}}, "/nonexistent/physics.json"),
        ), patch.object(
            api_module,
            "run_full_pipeline",
            side_effect=RuntimeError("RAG timeout"),
        ), patch(
            "reasoning_engine.generate_reasoning",
            side_effect=RuntimeError("LLM unavailable"),
        ):
            resp = self.client.post("/analyze", json={"gene": "SNCA", "variant": "A53T"})

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data["pdb_content"])
        self.assertIsNone(data["physics_data"])
        self.assertEqual(data["evidence"], [])
        self.assertIn("pdb_missing", data["warnings"])
        self.assertIn("physics_missing", data["warnings"])
        self.assertIn("literature_error", data["warnings"])
        # Deterministic fallback narrative still generated
        self.assertTrue(bool(data["clinical_narrative"]))

    def test_analyze_returns_500_when_scientific_pipeline_crashes(self):
        with patch.object(
            api_module,
            "run_pipeline",
            side_effect=RuntimeError("UniProt critical failure"),
        ):
            resp = self.client.post("/analyze", json={"gene": "SNCA", "variant": "A53T"})

        self.assertEqual(resp.status_code, 500)
        self.assertIn("Scientific pipeline execution failed", resp.json()["detail"])


class TestAPINonFunctional(unittest.TestCase):
    """Non-functional tests: security (CORS, secret isolation) & performance (latency, concurrency)."""

    def setUp(self):
        self.client = TestClient(api_module.app)

    def test_cors_allows_local_ui_and_blocks_untrusted_origin(self):
        allowed = self.client.options(
            "/analyze",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertEqual(
            allowed.headers.get("access-control-allow-origin"),
            "http://localhost:5173",
        )

        blocked = self.client.options(
            "/analyze",
            headers={
                "Origin": "https://malicious.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertIsNone(blocked.headers.get("access-control-allow-origin"))

    def test_error_and_success_responses_do_not_leak_api_keys(self):
        sentinel_secret = "sk-test-super-secret-token-987654321"
        with patch.dict(
            os.environ,
            {"GROQ_API_KEY": sentinel_secret, "OPENROUTER_API_KEY": sentinel_secret},
        ), patch.object(
            api_module,
            "run_pipeline",
            return_value=(None, {}, None),
        ), patch.object(
            api_module,
            "run_full_pipeline",
            return_value={"status": "SUCCESS", "evidence": []},
        ), patch(
            "reasoning_engine.generate_reasoning",
            return_value={"unstructured_verdict": "Clean response", "structured_data": None, "model_used": "mock"},
        ):
            resp = self.client.post("/analyze", json={"gene": "SNCA", "variant": "A53T"})

        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(sentinel_secret, resp.text)

    def test_health_endpoint_latency_sla(self):
        latencies_ms = []
        for _ in range(20):
            t0 = time.perf_counter()
            resp = self.client.get("/health")
            latencies_ms.append((time.perf_counter() - t0) * 1000.0)
            self.assertEqual(resp.status_code, 200)

        latencies_ms.sort()
        p95_ms = latencies_ms[int(0.95 * len(latencies_ms)) - 1]
        self.assertLess(p95_ms, 100.0, f"Health p95 latency too high: {p95_ms:.2f}ms")

    def test_concurrent_analyze_requests_thread_safety(self):
        def _run_one(idx: int):
            with TestClient(api_module.app) as client:
                resp = client.post(
                    "/analyze",
                    json={"gene": f"GENE{idx}", "variant": f"A{idx + 1}T"},
                )
                return resp.status_code, resp.json()

        with patch.object(
            api_module,
            "run_pipeline",
            return_value=(None, {}, None),
        ), patch.object(
            api_module,
            "run_full_pipeline",
            return_value={"status": "SUCCESS", "evidence": []},
        ), patch(
            "reasoning_engine.generate_reasoning",
            return_value={"unstructured_verdict": "OK", "structured_data": None, "model_used": "mock"},
        ):
            t0 = time.perf_counter()
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                results = list(pool.map(_run_one, range(10)))
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.assertEqual(len(results), 10)
        for idx, (code, body) in enumerate(results):
            self.assertEqual(code, 200)
            self.assertEqual(body["gene"], f"GENE{idx}")
            self.assertEqual(body["variant"], f"A{idx + 1}T")
        self.assertLess(elapsed_ms, 5000.0, f"10 concurrent requests took {elapsed_ms:.1f}ms")


if __name__ == "__main__":
    unittest.main()
