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
        self.assertFalse(is_scored_gptoss_run(_scored_row(model_meta={"provider": "groq", "model": "openai/gpt-oss-120b", "mode": "fallback_baseline"})))
        self.assertFalse(is_scored_gptoss_run(_scored_row(ablation="literature_only")))
        self.assertFalse(is_scored_gptoss_run(_scored_row(completed=False)))
        self.assertFalse(is_scored_gptoss_run(_scored_row(stage_status={"payload": "success"})))
        self.assertFalse(is_scored_gptoss_run(_scored_row(model="Llama 3.3 70B", model_meta={"provider": "openrouter", "model": "meta-llama/llama-3.3-70b-instruct", "mode": "api"})))

    def test_groq_keys_keep_primary_then_numbered(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "primary", "GROQ_API_KEY_1": "second", "GROQ_API_KEY_2": "primary"}, clear=False):
            self.assertEqual(_groq_keys(), ["primary", "second"])

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


if __name__ == "__main__":
    unittest.main()
