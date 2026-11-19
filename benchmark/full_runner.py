"""Full Neuro-Capstone benchmark runner.

This runner executes real repository stages for each ablation. It does not
interpret the physics heuristic as a clinical diagnosis. API-backed synthesis
is optional: without a provider key, the deterministic baseline records a
valid offline harness run and clearly identifies itself in the output.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import ssl
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from benchmark.benchmark import ABLATIONS, ROOT, calculate_metrics, load_gold, normalise_prediction, validate_payload, _clinical_class

OUT = ROOT / "data" / "benchmarks"
RUNS = OUT / "runs"

SYNTHESIS_SYSTEM_PROMPT = (
    "You are a cautious biomedical evidence synthesizer. Use only supplied evidence. "
    "Set prediction to exactly one of pathogenic, benign, or vus; use vus for conflicting, insufficient, or uncertain evidence. "
    "When ClinVar and a retrieved paper disagree, return vus rather than letting literature silently replace the clinical record. "
    "Preserve VUS uncertainty. Every factual claim must cite a supplied PMID or be explicitly marked as unsupported. "
    "Do not use gene-level evidence as exact-variant evidence. "
    "You may use the labeled site_description when choosing pathogenic, benign, or vus, and those values are not, by themselves, a folding effect or proof of either class, and they are not proof of pathogenicity; literature claims still need a supplied PMID. "
    "Return only JSON matching the schema."
)

SYNTHESIS_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["prediction", "conclusion", "uncertainty", "claims", "scope"],
    "properties": {
        "prediction": {"type": "string", "enum": ["pathogenic", "benign", "vus"]},
        "conclusion": {"type": "string"},
        "uncertainty": {"type": "boolean"},
        "scope": {"type": "string", "enum": ["variant", "gene", "unknown"]},
        "claims": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["text", "pmid", "claim_type"], "properties": {"text": {"type": "string"}, "pmid": {"type": ["string", "null"]}, "claim_type": {"type": "string"}}}},
    },
}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def _load_project_env() -> None:
    """Load simple KEY=VALUE entries from the project .env when present."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip("\"'")
        if name and name not in os.environ:
            os.environ[name] = value


_groq_cursor = 0


def _groq_keys() -> list[str]:
    """GROQ_API_KEY, then GROQ_API_KEY_1 .. GROQ_API_KEY_20, duplicates dropped."""
    ordered: list[str] = []
    seen: set[str] = set()
    for name in ("GROQ_API_KEY", *[f"GROQ_API_KEY_{index}" for index in range(1, 21)]):
        value = os.getenv(name, "").strip()
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _json_request(url: str, payload: dict[str, Any], key: str) -> dict[str, Any]:
    request = Request(url, data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "NeuroCapstoneBenchmark/1.0"})
    try:
        import certifi
        tls_context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        tls_context = ssl.create_default_context()
    with urlopen(request, timeout=120, context=tls_context) as response:
        return json.loads(response.read().decode())


def _baseline_synthesis(payload: dict[str, Any], target: dict[str, str]) -> dict[str, Any]:
    status = str(payload.get("status", "LOW_CONFIDENCE"))
    prediction = _clinical_class(payload.get("clinical_label")) or "vus"
    uncertain = prediction == "vus" or status != "SUCCESS"
    return {"prediction": prediction, "conclusion": "uncertain; evidence is insufficient for a definitive classification" if uncertain else f"evidence supports a {prediction} classification", "uncertainty": uncertain, "scope": "variant", "claims": []}


def _model_synthesis(payload: dict[str, Any], target: dict[str, str], spec: dict[str, str]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    global _groq_cursor
    provider = spec["provider"]
    if provider == "groq":
        keys = _groq_keys()
    else:
        openrouter = os.getenv("OPENROUTER_API_KEY", "").strip()
        keys = [openrouter] if openrouter else []
    if not keys:
        return None, {"provider": provider, "model": spec["model"], "mode": "api_failed", "error": "missing_api_key", "keys_tried": 0}
    endpoint = "https://api.groq.com/openai/v1/chat/completions" if provider == "groq" else "https://openrouter.ai/api/v1/chat/completions"
    system = SYNTHESIS_SYSTEM_PROMPT
    user = json.dumps({"target": target, "payload": payload}, ensure_ascii=False)
    request_payload = {"model": spec["model"], "temperature": 0, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "response_format": {"type": "json_schema", "json_schema": {"name": "evidence_synthesis", "strict": True, "schema": SYNTHESIS_SCHEMA}}}
    start = _groq_cursor % len(keys) if provider == "groq" else 0
    attempts = len(keys) if provider == "groq" else 1
    last_error: Exception | None = None
    tried = 0
    for offset in range(attempts):
        index = (start + offset) % len(keys)
        tried = offset + 1
        try:
            data = _json_request(endpoint, request_payload, keys[index])
            content = data["choices"][0]["message"]["content"]
            if provider == "groq":
                _groq_cursor = (index + 1) % len(keys)
            meta = {"provider": provider, "model": spec["model"], "mode": "api", "keys_tried": tried}
            if provider == "groq":
                meta["key_slot"] = index + 1
            return json.loads(content), meta
        except HTTPError as exc:
            last_error = exc
            if provider == "groq" and exc.code == 429 and offset + 1 < attempts:
                continue
            break
        except (KeyError, TypeError, ValueError, URLError, TimeoutError) as exc:
            last_error = exc
            break
    if provider == "groq":
        _groq_cursor = (start + 1) % len(keys)
    error = f"{type(last_error).__name__}: {last_error}" if last_error else "request_failed"
    meta = {"provider": provider, "model": spec["model"], "mode": "api_failed", "error": error, "keys_tried": tried}
    return None, meta


def _check_synthesis(synthesis: dict[str, Any], payload: dict[str, Any], target: dict[str, str]) -> tuple[bool, list[dict[str, Any]], bool, bool]:
    valid = isinstance(synthesis, dict) and all(key in synthesis for key in SYNTHESIS_SCHEMA["required"]) and isinstance(synthesis.get("claims"), list) and synthesis.get("prediction") in {"pathogenic", "benign", "vus"} and isinstance(synthesis.get("uncertainty"), bool)
    evidence = payload.get("evidence", [])
    pmids = {str(item.get("pmid")) for item in evidence}
    checks = []
    for claim in synthesis.get("claims", []) if isinstance(synthesis.get("claims"), list) else []:
        pmid = claim.get("pmid") if isinstance(claim, dict) else None
        checks.append({"pmid": pmid, "citation_valid": pmid is not None and str(pmid) in pmids, "unsupported": pmid is None or str(pmid) not in pmids, "scope_mistake": target["variant"].lower() not in str(claim).lower() and target["gene"].lower() not in str(claim).lower()})
    uncertainty = synthesis.get("uncertainty") is True or normalise_prediction(synthesis) == "vus"
    return valid, checks, uncertainty, any(check["scope_mistake"] for check in checks)


def _run_stages(target: dict[str, str], ablation: str, run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Execute the actual project stages according to the ablation."""
    from pipeline import run_pipeline
    from assemble_payload import run as assemble

    use_clinical = ablation in {"clinical_only", "all_evidence"}
    use_physics = ablation in {"physics_only", "all_evidence"}
    use_literature = ablation in {"literature_only", "all_evidence"}
    stage: dict[str, Any] = {"structure": "skipped", "clinical": "skipped", "physics": "skipped", "literature_fetch": "skipped", "literature_process": "skipped", "retrieval": "skipped", "payload": "pending"}
    # vector_engine currently reads its corpus from data/literature, so keep
    # that repository-defined cache location while isolating physics artifacts
    # and benchmark outputs under the run directory.
    pdb_path, context, physics_path = run_pipeline(target["gene"], target["variant"], run_structure=use_physics, run_context=use_clinical, run_analysis=use_physics, run_fetch_literature=use_literature, run_process_literature=use_literature, literature_dir=str(ROOT / "data" / "literature"), analysis_out_dir=str(run_dir / "analysis"))
    physics = json.loads(Path(physics_path).read_text()) if physics_path else None
    if not use_physics:
        physics_stage = "skipped"
    elif not isinstance(physics, dict):
        physics_stage = "failed"
    elif isinstance(physics.get("monomer_ddg"), (int, float)) and not isinstance(physics.get("monomer_ddg"), bool):
        physics_stage = "success"
    else:
        physics_stage = "incomplete"
    stage.update({"structure": "success" if pdb_path else "skipped", "clinical": "success" if context else ("skipped" if not use_clinical else "empty"), "physics": physics_stage, "literature_fetch": "success" if use_literature else "skipped", "literature_process": "success" if use_literature else "skipped"})
    ranked: list[dict[str, Any]] = []
    rag_status = "NULL_RESULTS"
    if use_literature:
        from orchestration import phase_3_vector_engine
        try:
            ranked = phase_3_vector_engine(target["gene"], target["variant"], f"{target['gene']} {target['variant']}")
        except Exception as exc:
            if type(exc).__name__ == "EmptyCorpusError":
                ranked = []
            else:
                raise
        rag_status = "SUCCESS" if ranked else "NULL_RESULTS"
        stage["retrieval"] = "success" if ranked else "empty"
    payload = assemble(query=f"{target['gene']} {target['variant']}", ranked_results=ranked, output_path=str(run_dir / "payload.json"), physics_vector=physics, rag_status=rag_status, clinical_context=context)
    if context:
        payload["clinical_context"] = context
        clinvar = context.get("clinvar") if isinstance(context, dict) else None
        if isinstance(clinvar, dict):
            payload["clinical_label"] = clinvar.get("clinical_significance", "")
    stage["payload"] = "success"
    return payload, stage


def run_full(gold_path: Path, *, model_specs: list[dict[str, str]], ablations: tuple[str, ...] = ABLATIONS) -> list[dict[str, Any]]:
    _load_project_env()
    targets = load_gold(gold_path)
    OUT.mkdir(parents=True, exist_ok=True)
    RUNS.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    stage_cache: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]] = {}
    for target in targets:
        for ablation in ablations:
            for spec in model_specs:
                run_id = hashlib.sha256(f"{target['variant_id']}:{ablation}:{spec.get('name','baseline')}".encode()).hexdigest()[:16]
                run_dir = RUNS / run_id
                run_dir.mkdir(parents=True, exist_ok=True)
                started = time.perf_counter()
                row = {"run_id": run_id, "variant_id": target["variant_id"], "gene": target["gene"], "variant": target["variant"], "gold_label": target["label"], "ablation": ablation, "model": spec.get("name", "deterministic baseline"), "started_at": _now(), "completed": False, "stage_status": {}}
                try:
                    cache_key = (target["variant_id"], ablation)
                    if cache_key not in stage_cache:
                        stage_cache[cache_key] = _run_stages(target, ablation, run_dir)
                    payload, stages = stage_cache[cache_key]
                    (run_dir / "payload.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
                    synthesis, model_meta = _model_synthesis(payload, target, spec) if spec.get("provider") else (_baseline_synthesis(payload, target), {"mode": "deterministic_baseline"})
                    clinical = payload.get("clinical_context", {}).get("clinvar", {}) if isinstance(payload.get("clinical_context"), dict) else {}
                    thermompnn = payload.get("thermompnn") if isinstance(payload.get("thermompnn"), dict) else {}
                    synthesis_path = run_dir / "synthesis.json"
                    if synthesis is None:
                        failed_synthesis = {"prediction": None, "conclusion": None, "uncertainty": None, "scope": None, "claims": [], "error": model_meta.get("error")}
                        synthesis_path.write_text(json.dumps(failed_synthesis, indent=2), encoding="utf-8")
                        row.update({
                            "completed": False,
                            "stage_status": stages,
                            "model_meta": model_meta,
                            "payload_path": str((run_dir / "payload.json").relative_to(OUT)),
                            "synthesis_path": str(synthesis_path.relative_to(OUT)),
                            "json_schema_valid": False,
                            "claim_checks": [],
                            "exact_clinvar_match": clinical.get("variant_match") is True,
                            "top5_evidence_count": len(payload.get("evidence", [])[:5]),
                            "top5_variant_mentions": sum(target["gene"].lower() in str(item).lower() and target["variant"].lower() in str(item).lower() for item in payload.get("evidence", [])[:5]),
                            "prediction": None,
                            "clinical_agreement": None,
                            "uncertainty_preserved": None,
                            "scope_mistake": False,
                            "external_api_failure": True,
                            "error": model_meta.get("error"),
                            "thermompnn_status": thermompnn.get("status"),
                            "thermompnn_error": thermompnn.get("error"),
                            "synthesis": failed_synthesis,
                        })
                    else:
                        synthesis_path.write_text(json.dumps(synthesis, indent=2), encoding="utf-8")
                        schema_ok, claims, uncertainty, scope_mistake = _check_synthesis(synthesis, payload, target)
                        predicted = normalise_prediction(synthesis)
                        physics_complete = stages.get("physics") not in {"incomplete", "failed"}
                        row.update({"completed": physics_complete, "stage_status": stages, "model_meta": model_meta, "payload_path": str((run_dir / "payload.json").relative_to(OUT)), "synthesis_path": str(synthesis_path.relative_to(OUT)), "json_schema_valid": schema_ok, "claim_checks": claims, "exact_clinvar_match": clinical.get("variant_match") is True, "top5_evidence_count": len(payload.get("evidence", [])[:5]), "top5_variant_mentions": sum(target["gene"].lower() in str(item).lower() and target["variant"].lower() in str(item).lower() for item in payload.get("evidence", [])[:5]), "prediction": predicted, "clinical_agreement": None if target["label"] == "unsettled" else predicted == target["label"], "uncertainty_preserved": uncertainty, "scope_mistake": scope_mistake, "thermompnn_status": thermompnn.get("status"), "thermompnn_error": thermompnn.get("error"), "synthesis": synthesis})
                except Exception as exc:
                    error_type = type(exc).__name__
                    row.update({"stage_status": {"pipeline_entry": "failed"}, "error_type": error_type, "error": str(exc), "external_api_failure": error_type in {"HTTPError", "URLError", "TimeoutError", "ConnectionError"}, "compatibility_failure": error_type in {"ModuleNotFoundError", "TypeError", "ImportError"}})
                row["runtime_seconds"] = round(time.perf_counter() - started, 4)
                row["finished_at"] = _now()
                rows.append(row)
    (OUT / "results.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    write_metrics(rows, OUT / "metrics.json")
    return rows


FULL_PIPELINE_STAGES = ("structure", "clinical", "physics", "literature_fetch", "literature_process", "retrieval", "payload")


def _is_gpt_oss(row: dict[str, Any]) -> bool:
    meta = row.get("model_meta") if isinstance(row.get("model_meta"), dict) else {}
    return "gpt-oss" in f"{row.get('model', '')} {meta.get('model', '')}".lower()


DUPLICATE_VARIANT_ALIASES = {
    "ttr-a45t": "ttr-a25t",
}


def _is_duplicate_variant(row: dict[str, Any]) -> bool:
    return bool(row.get("duplicate_of")) or str(row.get("variant_id", "")) in DUPLICATE_VARIANT_ALIASES


def is_scored_gptoss_run(row: dict[str, Any]) -> bool:
    """True when every full-pipeline stage succeeded and GPT-OSS returned an API synthesis."""
    if _is_duplicate_variant(row):
        return False
    if row.get("completed") is not True or row.get("ablation") != "all_evidence":
        return False
    meta = row.get("model_meta") if isinstance(row.get("model_meta"), dict) else {}
    if not _is_gpt_oss(row) or meta.get("mode") != "api":
        return False
    stages = row.get("stage_status") if isinstance(row.get("stage_status"), dict) else {}
    return all(stages.get(stage) == "success" for stage in FULL_PIPELINE_STAGES)


def exclusion_reason(row: dict[str, Any]) -> str | None:
    """Why a recorded run is left out of the scored benchmark, if it is."""
    if is_scored_gptoss_run(row):
        return None
    if _is_duplicate_variant(row):
        return "duplicate_variant"
    meta = row.get("model_meta") if isinstance(row.get("model_meta"), dict) else {}
    if meta.get("mode") == "api_failed":
        return "model_api_failed"
    stages = row.get("stage_status") if isinstance(row.get("stage_status"), dict) else {}
    if stages.get("physics") in {"incomplete", "failed"}:
        return "stage_not_successful"
    if row.get("completed") is not True:
        return "pipeline_failed"
    if row.get("ablation") != "all_evidence":
        return "partial_pipeline"
    if not all(stages.get(stage) == "success" for stage in FULL_PIPELINE_STAGES):
        return "stage_not_successful"
    return "gptoss_not_successful"


def scored_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if is_scored_gptoss_run(row)]


def relabel_rows_from_gold(rows: list[dict[str, Any]], gold_path: Path) -> list[dict[str, Any]]:
    """Sync recorded result rows with the curated literature labels in gold_variants.csv."""
    by_variant = {row["variant_id"]: row for row in load_gold(gold_path)}
    updated: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        variant_id = str(item.get("variant_id", ""))
        canonical = DUPLICATE_VARIANT_ALIASES.get(variant_id)
        if canonical and variant_id not in by_variant:
            item["duplicate_of"] = canonical
            item["clinical_agreement"] = None
            updated.append(item)
            continue
        item.pop("duplicate_of", None)
        gold = by_variant.get(variant_id)
        if gold is not None:
            item["gold_label"] = gold["label"]
            if gold.get("label_source"):
                item["label_source"] = gold["label_source"]
            if item.get("completed") is True:
                predicted = normalise_prediction(item.get("prediction", item.get("synthesis")))
                item["clinical_agreement"] = None if gold["label"] == "unsettled" else (predicted == gold["label"])
        updated.append(item)
    return updated


def write_html_report(rows: list[dict[str, Any]], path: Path) -> None:
    scored = scored_rows(rows)
    metrics = calculate_metrics(scored)
    def pct(value: Any) -> str:
        return "n/a" if value is None else f"{float(value) * 100:.1f}%"
    summary_keys = (
        "pipeline_completion_rate",
        "exact_variant_clinical_lookup_accuracy",
        "literature_relevance_top5",
        "citation_validity",
        "unsupported_claim_rate",
        "json_schema_validity",
        "mean_runtime_seconds",
        "external_api_failure_rate",
        "compatibility_failure_rate",
    )
    cards = "".join(
        f"<div class='card'><div class='label'>{html.escape(key.replace('_',' '))}</div><div class='value'>{html.escape(pct(metrics.get(key)) if isinstance(metrics.get(key),(float,int)) and 'runtime' not in key else str(metrics.get(key) if metrics.get(key) is not None else 'n/a'))}</div></div>"
        for key in summary_keys
    )
    reasons: dict[str, int] = {}
    for row in rows:
        reason = exclusion_reason(row)
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1
    exclusion_rows = "".join(f"<tr><td>{html.escape(reason)}</td><td>{count}</td></tr>" for reason, count in sorted(reasons.items())) or "<tr><td colspan='2'>None</td></tr>"
    ablation_rows = "".join(f"<tr><td>{html.escape(a)}</td><td>{pct(v.get('completion_rate'))}</td><td>{pct(v.get('literature_relevance_top5'))}</td><td>{pct(v.get('citation_validity'))}</td><td>{pct(v.get('vus_uncertainty_preservation'))}</td></tr>" for a,v in metrics.get("by_ablation", {}).items())
    class_rows = "".join(
        f"<tr><td>{html.escape(label)}</td><td>{values.get('n')}</td><td>{values.get('correct')}</td><td>{pct(values.get('agreement'))}</td></tr>"
        for label, values in metrics.get("prediction_by_class", {}).items()
    )
    document = f"<!doctype html><html><head><meta charset='utf-8'><title>Neuro-Capstone Benchmark</title><style>body{{font:15px system-ui;background:#f5f7fb;color:#172033;margin:32px}}h1{{color:#102a43}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}}.card,section{{background:white;border-radius:12px;padding:18px;box-shadow:0 2px 10px #102a4318;margin-bottom:18px}}.label{{color:#627d98;text-transform:capitalize}}.value{{font-size:25px;font-weight:700;margin-top:8px}}table{{width:100%;border-collapse:collapse}}td,th{{padding:9px;border-bottom:1px solid #e6e8ec;text-align:left}}th{{color:#486581}}code{{white-space:pre-wrap}}</style></head><body><h1>Neuro-Capstone benchmark</h1><p>Scored runs are full-pipeline cases only: every stage succeeded and GPT-OSS 120B returned an API synthesis. Physics is a heuristic, not a clinical diagnosis. Recorded {len(rows)}; scored {len(scored)}; unsettled variants excluded from agreement: {metrics.get('n_unsettled_excluded', 0)}.</p><div class='grid'>{cards}</div><section><h2>Ablation comparison</h2><table><tr><th>Setting</th><th>Completion</th><th>Top-5 relevance</th><th>Citation validity</th><th>VUS uncertainty</th></tr>{ablation_rows}</table></section><section><h2>Excluded runs</h2><table><tr><th>Reason</th><th>N</th></tr>{exclusion_rows}</table></section><section><h2>Settled literature-class agreement (reference only)</h2><p>Settled classes come from published literature named in gold_variants.csv. Unsettled variants ({metrics.get('n_unsettled_excluded', 0)}) are excluded rather than marked wrong. Because the settled benign/protective subset is tiny, this table is a reference check rather than a balanced clinical classifier benchmark.</p><table><tr><th>Gold class</th><th>N</th><th>Correct</th><th>Agreement</th></tr>{class_rows}</table></section></body></html>"
    path.write_text(document, encoding="utf-8")


def write_model_comparison(rows: list[dict[str, Any]], path: Path) -> None:
    rows = scored_rows(rows)
    fields = ["model", "n_runs", "completion_rate", "prediction_accuracy", "pathogenic_benign_agreement", "pathogenic_benign_macro_agreement", "citation_validity", "unsupported_claim_rate", "json_schema_validity", "vus_uncertainty_preservation", "scope_mistake_rate"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for model in sorted({str(row.get("model", "")) for row in rows}):
            subset = [row for row in rows if row.get("model") == model]
            metrics = calculate_metrics(subset)
            writer.writerow({"model": model, "n_runs": len(subset), "completion_rate": metrics["completion_rate"], "prediction_accuracy": metrics["prediction_accuracy"], "pathogenic_benign_agreement": metrics["pathogenic_benign_agreement"], "pathogenic_benign_macro_agreement": metrics["pathogenic_benign_macro_agreement"], "citation_validity": metrics["citation_validity"], "unsupported_claim_rate": metrics["unsupported_claim_rate"], "json_schema_validity": metrics["json_schema_validity"], "vus_uncertainty_preservation": metrics["vus_uncertainty_preservation"], "scope_mistake_rate": round(sum(bool(row.get("scope_mistake")) for row in subset) / len(subset), 4) if subset else None})


def write_metrics(rows: list[dict[str, Any]], path: Path) -> None:
    metrics = calculate_metrics(scored_rows(rows))
    metrics["n_recorded"] = len(rows)
    metrics["n_scored"] = metrics["n_runs"]
    metrics["n_excluded"] = len(rows) - metrics["n_runs"]
    path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")


def write_markdown_report(rows: list[dict[str, Any]], path: Path) -> None:
    scored = scored_rows(rows)
    metrics = calculate_metrics(scored)
    reasons: dict[str, int] = {}
    for row in rows:
        reason = exclusion_reason(row)
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1
    lines = [
        "# Neuro-Capstone benchmark report",
        "",
        "Scored runs are limited to cases where the full pipeline succeeded and GPT-OSS 120B returned an API synthesis. That means the all_evidence setting, with structure, clinical context, physics, literature fetch, literature processing, retrieval, and payload each marked success, and model_meta.mode equal to api. Partial ablations, pipeline failures, and fallback baselines are excluded. Physics is a heuristic and is not treated as a clinical diagnosis.",
        "",
        f"Recorded runs: {len(rows)}. Scored runs: {len(scored)}. Unsettled variants excluded from agreement: {metrics.get('n_unsettled_excluded', 0)}.",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key in (
        "n_runs",
        "pipeline_completion_rate",
        "exact_variant_clinical_lookup_accuracy",
        "literature_relevance_top5",
        "citation_validity",
        "unsupported_claim_rate",
        "json_schema_validity",
        "n_unsettled_excluded",
        "mean_runtime_seconds",
        "external_api_failure_rate",
        "compatibility_failure_rate",
    ):
        lines.append(f"| {key} | {metrics.get(key)} |")
    lines.extend(["", "## Ablation comparison", "", "| Setting | Completion | Top-5 relevance | Citation validity | VUS uncertainty |", "|---|---:|---:|---:|---:|"])
    for ablation, values in metrics.get("by_ablation", {}).items():
        lines.append(f"| {ablation} | {values.get('completion_rate')} | {values.get('literature_relevance_top5')} | {values.get('citation_validity')} | {values.get('vus_uncertainty_preservation')} |")
    lines.extend(["", "## Excluded runs", "", "| Reason | N |", "|---|---:|"])
    for reason, count in sorted(reasons.items()):
        lines.append(f"| {reason} | {count} |")
    lines.extend([
        "",
        "## Settled literature-class agreement (reference only)",
        "",
        "Settled labels come from published literature named in `data/benchmarks/gold_variants.csv`, not ClinVar class strings alone. Variants left unsettled by published reviews are excluded from agreement rather than marked wrong when the model chooses a class. Because only two settled benign/protective variants appear in this 35-variant set (`TTR T139M` protective and `TTR G26S` polymorphism), this table is a reference sanity check rather than a balanced clinical benchmark; blinded rescue-set AUROC is tracked separately.",
        "",
        f"Overall settled agreement: {metrics.get('pathogenic_benign_agreement')} (unsettled excluded: {metrics.get('n_unsettled_excluded', 0)}).",
        "",
        "| Gold class | N | Correct | Agreement |",
        "|---|---:|---:|---:|",
    ])
    for label, values in metrics.get("prediction_by_class", {}).items():
        lines.append(f"| {label} | {values.get('n')} | {values.get('correct')} | {values.get('agreement')} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def publish_reports(rows: list[dict[str, Any]], html_path: Path | None = None) -> list[dict[str, Any]]:
    """Write metrics and reports for full-pipeline GPT-OSS successes only."""
    write_metrics(rows, OUT / "metrics.json")
    write_html_report(rows, html_path or (OUT / "benchmark_report.html"))
    write_model_comparison(rows, OUT / "model_comparison.csv")
    write_markdown_report(rows, OUT / "benchmark_report.md")
    write_markdown_report(rows, OUT / "gbenchmark_report.md")
    return scored_rows(rows)


def main() -> int:
    _load_project_env()
    parser = argparse.ArgumentParser(description="Run the full Neuro-Capstone benchmark")
    parser.add_argument("--gold", type=Path, default=OUT / "gold_variants.csv")
    parser.add_argument("--models", type=Path, default=ROOT / "benchmark" / "model_catalog.json")
    parser.add_argument("--model", help="Run only the catalog model with this name or provider model ID")
    parser.add_argument("--ablation", action="append", choices=ABLATIONS)
    parser.add_argument("--html", type=Path, default=OUT / "benchmark_report.html")
    args = parser.parse_args()
    catalog = json.loads(args.models.read_text()).get("models", [])
    if args.model:
        configured = [model for model in catalog if args.model in {model.get("name"), model.get("model")}]
        if not configured:
            parser.error(f"no catalog model matched {args.model!r}")
    else:
        configured = [model for model in catalog if model.get("enabled")]
    if os.getenv("BENCHMARK_OFFLINE", "").lower() in {"1", "true", "yes"} or not configured:
        configured = [{"name": "deterministic baseline"}]
    rows = run_full(args.gold, model_specs=configured, ablations=tuple(args.ablation or ABLATIONS))
    scored = publish_reports(rows, args.html)
    print(f"recorded {len(rows)} runs, scored {len(scored)} full-pipeline GPT-OSS runs, {args.html}, {OUT / 'benchmark_report.md'}, and {OUT / 'model_comparison.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
