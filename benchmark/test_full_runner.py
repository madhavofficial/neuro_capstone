import json
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import benchmark.full_runner as runner
from benchmark.full_runner import FULL_PIPELINE_STAGES, SYNTHESIS_SYSTEM_PROMPT, _groq_keys, _model_synthesis, is_scored_gptoss_run, write_html_report, write_markdown_report, write_model_comparison


def _scored_row(**overrides):
    row = {
        "run_id": "ok",
        "variant": "A53T",
        "ablation": "all_evidence",
        "model": "GPT-OSS 120B",
        "completed": True,
        "gold_label": "pathogenic",
        "json_schema_valid": True,
        "claim_checks": [],
        "top5_evidence_count": 1,
        "top5_variant_mentions": 1,
        "uncertainty_preserved": False,
        "runtime_seconds": 1.0,
        "prediction": "pathogenic",
        "external_api_failure": False,
        "stage_status": {stage: "success" for stage in FULL_PIPELINE_STAGES},
        "model_meta": {"provider": "groq", "model": "openai/gpt-oss-120b", "mode": "api"},
    }
    row.update(overrides)
    return row


class FullRunnerTests(unittest.TestCase):
    def test_visual_and_comparison_outputs(self):
        fallback = _scored_row(run_id="fb", ablation="clinical_only", model_meta={"provider": "groq", "model": "openai/gpt-oss-120b", "mode": "fallback_baseline"})
        rows = [_scored_row(), fallback]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_html_report(rows, root / "report.html")
            write_markdown_report(rows, root / "report.md")
            write_model_comparison(rows, root / "models.csv")
            html_report = (root / "report.html").read_text()
            markdown = (root / "report.md").read_text()
            comparison = (root / "models.csv").read_text()
            self.assertIn("Ablation comparison", html_report)
            self.assertIn("Excluded runs", html_report)
            self.assertIn("benchmark report", markdown)
            self.assertIn("Scored runs: 1", markdown)
            self.assertIn("partial_pipeline", markdown)
            self.assertIn("GPT-OSS 120B,1,", comparison)
            self.assertNotIn("clinical_only", comparison)

    def test_scoring_keeps_full_pipeline_gptoss_api_only(self):
        self.assertTrue(is_scored_gptoss_run(_scored_row()))
        self.assertFalse(is_scored_gptoss_run(_scored_row(duplicate_of="ttr-a25t")))
        self.assertEqual(runner.exclusion_reason(_scored_row(duplicate_of="ttr-a25t")), "duplicate_variant")
        self.assertFalse(is_scored_gptoss_run(_scored_row(variant_id="ttr-a45t")))
        self.assertEqual(runner.exclusion_reason(_scored_row(variant_id="ttr-a45t")), "duplicate_variant")
        for bad_physics in ("incomplete", "failed"):
            bad_physics_row = _scored_row(
                completed=False,
                stage_status={**{stage: "success" for stage in FULL_PIPELINE_STAGES}, "physics": bad_physics},
            )
            self.assertFalse(is_scored_gptoss_run(bad_physics_row))
            self.assertEqual(runner.exclusion_reason(bad_physics_row), "stage_not_successful")
        self.assertFalse(is_scored_gptoss_run(_scored_row(model_meta={"provider": "groq", "model": "openai/gpt-oss-120b", "mode": "fallback_baseline"})))
        self.assertFalse(is_scored_gptoss_run(_scored_row(ablation="literature_only")))
        self.assertFalse(is_scored_gptoss_run(_scored_row(completed=False)))
        self.assertFalse(is_scored_gptoss_run(_scored_row(stage_status={"payload": "success"})))
        self.assertFalse(is_scored_gptoss_run(_scored_row(model="Llama 3.3 70B", model_meta={"provider": "openrouter", "model": "meta-llama/llama-3.3-70b-instruct", "mode": "api"})))

    def test_groq_keys_keep_primary_then_numbered(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "primary", "GROQ_API_KEY_1": "second", "GROQ_API_KEY_2": "primary", "GROQ_API_KEYS": "third, second"}, clear=False):
            self.assertEqual(_groq_keys(), ["primary", "second", "third"])

    def test_model_fallback_steps_in_when_primary_model_hits_429_across_keys(self):
        calls: list[tuple[str, str]] = []

        def fake_request(url, payload, key):
            calls.append((payload["model"], key))
            if payload["model"] == "openai/gpt-oss-120b":
                raise HTTPError(url, 429, "Too Many Requests", hdrs=None, fp=BytesIO(b""))
            return {"choices": [{"message": {"content": '{"prediction":"vus","conclusion":"uncertain","uncertainty":true,"scope":"variant","claims":[]}'}}]}

        runner._groq_cursor = 0
        spec = {
            "provider": "groq",
            "model": "openai/gpt-oss-120b",
            "fallback_models": [
                {"provider": "groq", "model": "openai/gpt-oss-20b"},
                {"provider": "groq", "model": "llama-3.3-70b-versatile"},
            ],
        }
        with patch.dict(os.environ, {"GROQ_API_KEY": "k1", "GROQ_API_KEY_1": "k2"}, clear=False), \
             patch.object(runner, "_json_request", side_effect=fake_request):
            synthesis, meta = _model_synthesis({}, {"gene": "SNCA", "variant": "A53T"}, spec)

        self.assertEqual(calls, [("openai/gpt-oss-120b", "k1"), ("openai/gpt-oss-120b", "k2"), ("openai/gpt-oss-20b", "k2")])
        self.assertEqual(meta["mode"], "api")
        self.assertEqual(meta["model"], "openai/gpt-oss-20b")
        self.assertEqual(meta["requested_model"], "openai/gpt-oss-120b")
        self.assertTrue(meta["fallback_used"])
        self.assertEqual(meta["keys_tried"], 3)
        self.assertEqual(synthesis["prediction"], "vus")
        self.assertNotIn("k1", str(meta))
        self.assertNotIn("k2", str(meta))

    def test_429_tries_the_next_groq_key(self):
        seen: list[str] = []

        def fake_request(url, payload, key):
            seen.append(key)
            if key == "primary":
                raise HTTPError(url, 429, "Too Many Requests", hdrs=None, fp=BytesIO(b""))
            return {"choices": [{"message": {"content": '{"prediction":"vus","conclusion":"uncertain","uncertainty":true,"scope":"variant","claims":[]}'}}]}

        runner._groq_cursor = 0
        spec = {"provider": "groq", "model": "openai/gpt-oss-120b"}
        with patch.dict(os.environ, {"GROQ_API_KEY": "primary", "GROQ_API_KEY_1": "second"}, clear=False), patch.object(runner, "_json_request", fake_request):
            synthesis, meta = _model_synthesis({}, {"gene": "SNCA", "variant": "A53T"}, spec)
        self.assertEqual(seen, ["primary", "second"])
        self.assertEqual(meta["mode"], "api")
        self.assertEqual(meta["key_slot"], 2)
        self.assertEqual(meta["keys_tried"], 2)
        self.assertEqual(synthesis["prediction"], "vus")
        self.assertNotIn("primary", str(meta))
        self.assertNotIn("second", str(meta))

    def test_system_prompt_may_use_labeled_site_description(self):
        prompt = SYNTHESIS_SYSTEM_PROMPT
        self.assertIn("may use the labeled site_description", prompt)
        self.assertIn("choosing pathogenic, benign, or vus", prompt)
        self.assertIn("not, by themselves, a folding effect", prompt)
        self.assertIn("not proof of pathogenicity", prompt)
        self.assertIn("literature claims still need a supplied PMID", prompt)
        self.assertIn("When ClinVar and a retrieved paper disagree, return vus", prompt)

    def test_failed_model_call_returns_none_not_clinvar_class(self):
        payload = {"status": "SUCCESS", "clinical_label": "Pathogenic", "evidence": [{"pmid": "111", "title": "t", "text": "x"}]}
        spec = {"provider": "groq", "model": "openai/gpt-oss-120b"}
        runner._groq_cursor = 0

        def always_429(url, req_payload, key):
            raise HTTPError(url, 429, "Too Many Requests", hdrs=None, fp=BytesIO(b""))

        with patch.dict(os.environ, {"GROQ_API_KEY": "k1", "GROQ_API_KEY_1": "k2"}, clear=False), \
             patch.object(runner, "_json_request", side_effect=always_429):
            synthesis, meta = _model_synthesis(payload, {"gene": "SNCA", "variant": "A53T"}, spec)

        self.assertIsNone(synthesis)
        self.assertEqual(meta["mode"], "api_failed")
        self.assertEqual(meta["keys_tried"], 2)
        self.assertIn("429", meta["error"])

    def test_run_full_records_failed_model_call_as_failed_row_and_separates_in_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gold_path = root / "gold.csv"
            gold_path.write_text(
                "variant_id,gene,variant,label,label_source,clinvar_variation_id,review_status,condition,source_url,date_retrieved\n"
                "snca-a53t,SNCA,A53T,pathogenic,Polymeropoulos 1997,14007,retrieved,PD,https://example.org,2026-08-17\n",
                encoding="utf-8",
            )
            fake_payload = {
                "status": "SUCCESS",
                "query": "SNCA A53T",
                "clinical_label": "Pathogenic",
                "clinical_context": {"clinvar": {"variant_match": True, "clinical_significance": "Pathogenic"}},
                "thermompnn": {"status": "scored", "monomer_ddg": 1.2},
                "evidence": [{"pmid": "9197268", "title": "SNCA A53T", "text": "SNCA A53T study"}],
            }
            fake_stages = {stage: "success" for stage in FULL_PIPELINE_STAGES}
            spec = {"name": "GPT-OSS 120B", "provider": "groq", "model": "openai/gpt-oss-120b"}

            def always_timeout(url, req_payload, key):
                raise TimeoutError("timed out")

            with patch.object(runner, "OUT", root), \
                 patch.object(runner, "RUNS", root / "runs"), \
                 patch.object(runner, "_run_stages", return_value=(fake_payload, fake_stages)), \
                 patch.dict(os.environ, {"GROQ_API_KEY": "k1"}, clear=False), \
                 patch.object(runner, "_json_request", side_effect=always_timeout):
                rows = runner.run_full(gold_path, model_specs=[spec], ablations=("all_evidence",))

            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertFalse(row["completed"])
            self.assertIsNone(row["prediction"])
            self.assertIsNone(row["clinical_agreement"])
            self.assertEqual(row["claim_checks"], [])
            self.assertEqual(row["synthesis"]["claims"], [])
            self.assertIsNone(row["synthesis"]["prediction"])
            self.assertTrue(row["external_api_failure"])
            self.assertEqual(row["model_meta"]["mode"], "api_failed")
            self.assertEqual(runner.exclusion_reason(row), "model_api_failed")
            self.assertFalse(is_scored_gptoss_run(row))

            report_path = root / "report.md"
            write_markdown_report(rows, report_path)
            markdown = report_path.read_text(encoding="utf-8")
            self.assertIn("Scored runs: 0", markdown)
            self.assertIn("| model_api_failed | 1 |", markdown)

    def test_successful_conflict_call_returns_vus_without_replacing_clinvar(self):
        payload = {
            "status": "SUCCESS",
            "clinical_label": "Pathogenic",
            "evidence": [{"pmid": "29331259", "title": "H50Q not pathogenic", "text": "Insufficient evidence for pathogenicity"}],
        }
        spec = {"provider": "groq", "model": "openai/gpt-oss-120b"}

        def conflict_response(url, req_payload, key):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"prediction":"vus","conclusion":"ClinVar and retrieved literature conflict.","uncertainty":true,"scope":"variant","claims":[{"text":"Insufficient evidence for pathogenicity","pmid":"29331259","claim_type":"literature"}]}'
                        }
                    }
                ]
            }

        with patch.dict(os.environ, {"GROQ_API_KEY": "k1"}, clear=False), \
             patch.object(runner, "_json_request", side_effect=conflict_response):
            synthesis, meta = _model_synthesis(payload, {"gene": "SNCA", "variant": "H50Q"}, spec)

        self.assertEqual(meta["mode"], "api")
        self.assertEqual(synthesis["prediction"], "vus")
        self.assertTrue(synthesis["uncertainty"])
        self.assertEqual(payload["clinical_label"], "Pathogenic")

    def test_empty_corpus_completes_row_with_no_results_and_model_sees_empty_evidence(self):
        class EmptyCorpusError(RuntimeError):
            pass

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gold_path = root / "gold.csv"
            gold_path.write_text(
                "variant_id,gene,variant,label,label_source,clinvar_variation_id,review_status,condition,source_url,date_retrieved\n"
                "ttr-v48m,TTR,V48M,unsettled,Unsettled,4193819,retrieved,ATTR,https://example.org,2026-08-17\n",
                encoding="utf-8",
            )
            physics_file = root / "TTR_V48M_physics.json"
            physics_file.write_text('{"deltas": {"delta_volume": 10.0}, "monomer_ddg": 0.3}', encoding="utf-8")
            seen_payloads = []

            def fake_run_pipeline(*args, **kwargs):
                return (str(root / "TTR.pdb"), {"clinvar": {"variant_match": True, "clinical_significance": "Uncertain significance"}}, str(physics_file))

            def fake_phase3(*args, **kwargs):
                raise EmptyCorpusError("Chunked corpus for TTR V48M contains 0 chunks")

            def fake_json_request(url, req_payload, key):
                seen_payloads.append(req_payload)
                return {
                    "choices": [
                        {
                            "message": {
                                "content": '{"prediction":"vus","conclusion":"No papers retrieved.","uncertainty":true,"scope":"variant","claims":[]}'
                            }
                        }
                    ]
                }

            spec = {"name": "GPT-OSS 120B", "provider": "groq", "model": "openai/gpt-oss-120b"}
            with patch.object(runner, "OUT", root), \
                 patch.object(runner, "RUNS", root / "runs"), \
                 patch("pipeline.run_pipeline", side_effect=fake_run_pipeline), \
                 patch("orchestration.phase_3_vector_engine", side_effect=fake_phase3), \
                 patch.dict(os.environ, {"GROQ_API_KEY": "k1"}, clear=False), \
                 patch.object(runner, "_json_request", side_effect=fake_json_request):
                rows = runner.run_full(gold_path, model_specs=[spec], ablations=("all_evidence",))

            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertTrue(row["completed"])
            self.assertEqual(row["stage_status"]["retrieval"], "empty")
            self.assertTrue(is_scored_gptoss_run(row))
            self.assertIsNone(runner.exclusion_reason(row))
            self.assertEqual(row["top5_evidence_count"], 0)
            self.assertEqual(len(seen_payloads), 1)
            saved_payload = runner.json.loads((root / row["payload_path"]).read_text(encoding="utf-8"))
            self.assertEqual(saved_payload["evidence"], [])
            self.assertEqual(saved_payload["confidence_matrix"]["literature_rag"], "NULL_RESULTS")

    def test_real_fetch_exception_stays_failed_and_distinct_from_empty_corpus(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gold_path = root / "gold.csv"
            gold_path.write_text(
                "variant_id,gene,variant,label,label_source,clinvar_variation_id,review_status,condition,source_url,date_retrieved\n"
                "ttr-v48m,TTR,V48M,unsettled,Unsettled,4193819,retrieved,ATTR,https://example.org,2026-08-17\n",
                encoding="utf-8",
            )
            spec = {"name": "GPT-OSS 120B", "provider": "groq", "model": "openai/gpt-oss-120b"}
            with patch.object(runner, "OUT", root), \
                 patch.object(runner, "RUNS", root / "runs"), \
                 patch("pipeline.run_pipeline", side_effect=TimeoutError("Europe PMC timed out")):
                rows = runner.run_full(gold_path, model_specs=[spec], ablations=("all_evidence",))

            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertFalse(row["completed"])
            self.assertEqual(row["error_type"], "TimeoutError")
            self.assertTrue(row["external_api_failure"])
            self.assertIn("Europe PMC timed out", row["error"])

    def test_physics_only_keeps_literature_stages_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            physics_file = root / "TTR_V48M_physics.json"
            physics_file.write_text('{"deltas": {"delta_volume": 10.0}, "monomer_ddg": 0.3}', encoding="utf-8")

            def fake_run_pipeline(*args, **kwargs):
                return (str(root / "TTR.pdb"), None, str(physics_file))

            with patch("pipeline.run_pipeline", side_effect=fake_run_pipeline):
                payload, stages = runner._run_stages({"variant_id": "ttr-v48m", "gene": "TTR", "variant": "V48M"}, "physics_only", root)

            self.assertEqual(stages["literature_fetch"], "skipped")
            self.assertEqual(stages["literature_process"], "skipped")
            self.assertEqual(stages["retrieval"], "skipped")
            self.assertEqual(stages["physics"], "success")
            self.assertEqual(payload["evidence"], [])

    def test_markdown_report_excludes_unsettled_and_does_not_lead_with_benign_agreement(self):
        rows = [
            _scored_row(run_id="p1", gold_label="pathogenic", prediction="pathogenic"),
            _scored_row(run_id="u1", gold_label="unsettled", prediction="pathogenic"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.md"
            write_markdown_report(rows, report_path)
            markdown = report_path.read_text(encoding="utf-8")
            summary_section = markdown.split("## Ablation comparison")[0]
            self.assertIn("Unsettled variants excluded from agreement: 1", markdown)
            self.assertNotIn("pathogenic_benign_agreement", summary_section)
            self.assertIn("## Settled literature-class agreement (reference only)", markdown)
            self.assertGreater(
                markdown.index("## Settled literature-class agreement (reference only)"),
                markdown.index("## Excluded runs"),
            )

    def test_model_synthesis_strips_gold_label_and_sources_from_prompt(self):
        captured: dict[str, object] = {}

        def fake_json_request(url, payload, key):
            captured["user"] = json.loads(payload["messages"][1]["content"])
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({
                                "prediction": "vus",
                                "conclusion": "uncertain",
                                "uncertainty": True,
                                "scope": "variant",
                                "claims": [],
                            })
                        }
                    }
                ]
            }

        target = {
            "variant_id": "ttr-v48m",
            "gene": "TTR",
            "variant": "V48M",
            "label": "pathogenic",
            "label_source": "ClinVar 4193819 Likely pathogenic",
            "clinvar_variation_id": "4193819",
            "condition": "ATTR",
        }
        spec = {"provider": "groq", "model": "openai/gpt-oss-120b"}
        with patch.object(runner, "_provider_keys", return_value=["fake-key"]), patch.object(runner, "_json_request", side_effect=fake_json_request):
            synthesis, meta = runner._model_synthesis({"status": "SUCCESS", "evidence": []}, target, spec)

        self.assertIsNotNone(synthesis)
        self.assertEqual(meta["mode"], "api")
        sent_target = captured["user"]["target"]
        self.assertEqual(sent_target, {"variant_id": "ttr-v48m", "gene": "TTR", "variant": "V48M"})
        for forbidden in ("label", "label_source", "clinvar_variation_id", "condition"):
            self.assertNotIn(forbidden, sent_target)


if __name__ == "__main__":
    unittest.main()
