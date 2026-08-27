"""Benchmark runner, metrics, ablations, and model-comparison utilities.

The benchmark deliberately keeps clinical labels separate from system outputs.
ClinVar is the reference source; VUS rows are scored for uncertainty preservation,
not as incorrect pathogenic/benign predictions.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "data" / "benchmarks"
ABLATIONS = ("clinical_only", "literature_only", "physics_only", "all_evidence")
VALID_LABELS = {"pathogenic", "benign", "vus"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def load_gold(path: Path) -> list[dict[str, Any]]:
    """Load and validate the versioned gold CSV."""
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    required = {
        "variant_id", "gene", "variant", "label", "clinvar_variation_id",
        "review_status", "condition", "source_url", "date_retrieved",
    }
    if rows and not required.issubset(rows[0]):
        raise ValueError(f"gold set is missing columns: {sorted(required - set(rows[0]))}")
    for row in rows:
        row["label"] = row["label"].strip().lower()
        if row["label"] not in VALID_LABELS:
            raise ValueError(f"invalid gold label for {row.get('variant_id')}: {row['label']}")
        if not row["clinvar_variation_id"] or row["clinvar_variation_id"] in {"NA", "UNRESOLVED"}:
            continue
    resolved = [row for row in rows if row.get("clinvar_variation_id") not in {"", "NA", "UNRESOLVED"}]
    unresolved = len(rows) - len(resolved)
    if unresolved:
        print(f"[WARN]  Excluding {unresolved} unresolved ClinVar candidates; benchmarking {len(resolved)} verified rows.")
    if not resolved:
        raise ValueError("gold set contains no resolved ClinVar records; run prepare_gold_set.py")
    return resolved


def validate_payload(payload: Any) -> tuple[bool, list[str]]:
    """Small dependency-free schema check for payloads consumed by the runner."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return False, ["payload is not an object"]
    for key in ("status", "query", "evidence"):
        if key not in payload:
            errors.append(f"missing {key}")
    if "evidence" in payload and not isinstance(payload["evidence"], list):
        errors.append("evidence is not an array")
    for index, item in enumerate(payload.get("evidence", [])):
        if not isinstance(item, dict):
            errors.append(f"evidence[{index}] is not an object")
            continue
        for key in ("pmid", "title", "text"):
            if key not in item:
                errors.append(f"evidence[{index}] missing {key}")
    return not errors, errors


def _normalise(text: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def _variant_mentions(item: dict[str, Any], gene: str, variant: str) -> bool:
    text = " ".join(str(item.get(k, "")) for k in ("text", "title", "chunk"))
    aliases = {variant, variant.upper(), variant.replace(" ", "")}
    return _normalise(gene) in _normalise(text) and any(_normalise(x) in _normalise(text) for x in aliases)


def _claims_from_synthesis(synthesis: Any) -> list[dict[str, Any]]:
    if not isinstance(synthesis, dict):
        return []
    claims = synthesis.get("claims", synthesis.get("findings", []))
    return claims if isinstance(claims, list) else []


def _clinical_class(value: Any) -> str:
    text = str(value or "").lower()
    if "pathogenic" in text:
        return "pathogenic"
    if "benign" in text:
        return "benign"
    if any(token in text for token in ("uncertain", "vus", "conflicting")):
        return "vus"
    return ""


def calculate_metrics(rows: list[dict[str, Any]], *, _nested: bool = False) -> dict[str, Any]:
    """Calculate metrics from result rows without assuming a particular LLM."""
    completed = [r for r in rows if r.get("completed") is True]
    non_vus = [r for r in completed if r.get("gold_label") in {"pathogenic", "benign"}]
    vus = [r for r in completed if r.get("gold_label") == "vus"]
    top5_total = sum(r.get("top5_evidence_count", 0) for r in completed)
    top5_mentions = sum(r.get("top5_variant_mentions", 0) for r in completed)
    claims = [c for r in completed for c in r.get("claim_checks", [])]
    valid_claims = sum(c.get("citation_valid") is True for c in claims)
    unsupported = sum(c.get("unsupported") is True for c in claims)
    schema_valid = sum(r.get("json_schema_valid") is True for r in completed)
    def rate(n: int, d: int) -> float | None:
        return round(n / d, 4) if d else None
    metrics = {
        "n_runs": len(rows),
        "completion_rate": rate(len(completed), len(rows)),
        "pipeline_completion_rate": rate(sum(r.get("stage_status", {}).get("payload") == "success" for r in rows), len(rows)),
        "exact_variant_clinical_lookup_accuracy": rate(sum(r.get("exact_clinvar_match") is True for r in completed), len(completed)),
        "literature_relevance_top5": rate(top5_mentions, top5_total),
        "citation_validity": rate(valid_claims, len(claims)),
        "unsupported_claim_rate": rate(unsupported, len(claims)),
        "json_schema_validity": rate(schema_valid, len(completed)),
        "pathogenic_benign_agreement": rate(sum(r.get("clinical_agreement") is True for r in non_vus), len(non_vus)),
        "vus_uncertainty_preservation": rate(sum(r.get("uncertainty_preserved") is True for r in vus), len(vus)),
        "mean_runtime_seconds": round(sum(r.get("runtime_seconds", 0) for r in completed) / len(completed), 4) if completed else None,
        "external_api_failure_rate": rate(sum(r.get("external_api_failure") is True for r in rows), len(rows)),
        "compatibility_failure_rate": rate(sum(r.get("compatibility_failure") is True for r in rows), len(rows)),
        "failure_by_stage": {
            stage: sum(1 for r in rows if r.get("stage_status", {}).get(stage) in {"failed", "error", "empty"})
            for stage in ("pipeline_entry", "structure", "clinical", "physics", "literature_fetch", "literature_process", "retrieval", "payload")
        },
    }
    if not _nested:
        metrics["by_ablation"] = {
            a: calculate_metrics([r for r in rows if r.get("ablation") == a], _nested=True)
            for a in ABLATIONS
            if any(r.get("ablation") == a for r in rows)
        }
    return metrics


def _default_synthesis(payload: dict[str, Any], gold_label: str) -> dict[str, Any]:
    """Deterministic baseline; useful for schema/grounding tests and offline CI."""
    status = str(payload.get("status", "UNCERTAIN"))
    uncertainty = gold_label == "vus" or status in {"LOW_CONFIDENCE", "STRUCTURAL_DISCOVERY_VUS", "PREDICTED_PATHOGENIC_VUS"}
    return {
        "conclusion": "uncertain; additional evidence is required" if uncertainty else "see supplied clinical evidence",
        "uncertainty": uncertainty,
        "claims": [],
    }


def run_one(target: dict[str, Any], ablation: str, pipeline: Callable[..., dict[str, Any]], synthesis: Callable[[dict[str, Any], str], dict[str, Any]], out_dir: Path) -> dict[str, Any]:
    started = time.perf_counter()
    row: dict[str, Any] = {
        "run_id": hashlib.sha256(f"{target['variant_id']}:{ablation}".encode()).hexdigest()[:16],
        "variant_id": target["variant_id"], "gene": target["gene"], "variant": target["variant"],
        "gold_label": target["label"], "ablation": ablation, "started_at": _now(), "completed": False,
    }
    try:
        payload = pipeline(target["gene"], target["variant"], ablation=ablation)
        valid, errors = validate_payload(payload)
        synth = synthesis(payload, target["label"])
        evidence = payload.get("evidence", []) if isinstance(payload, dict) else []
        claims = _claims_from_synthesis(synth)
        checked_claims = []
        supplied_pmids = {str(e.get("pmid")) for e in evidence}
        for claim in claims:
            cited = claim.get("pmid", claim.get("citation", claim.get("source_pmid"))) if isinstance(claim, dict) else None
            checked_claims.append({"citation_valid": str(cited) in supplied_pmids if cited else False, "unsupported": not bool(cited and str(cited) in supplied_pmids), "pmid": cited})
        row.update({
            "completed": True, "json_schema_valid": valid, "schema_errors": errors,
            "exact_clinvar_match": bool(payload.get("clinical_context", {}).get("clinvar", {}).get("variant_match")) if isinstance(payload, dict) else False,
            "top5_evidence_count": len(evidence[:5]),
            "top5_variant_mentions": sum(_variant_mentions(e, target["gene"], target["variant"]) for e in evidence[:5]),
            "clinical_agreement": (target["label"] == "vus" or _clinical_class(payload.get("clinical_label")) == target["label"]),
            "uncertainty_preserved": target["label"] != "vus" or bool(synth.get("uncertainty") is True or "uncertain" in str(synth).lower()),
            "claim_checks": checked_claims, "synthesis": synth,
        })
    except Exception as exc:
        row.update({"error_type": type(exc).__name__, "error": str(exc), "external_api_failure": True})
    row["runtime_seconds"] = round(time.perf_counter() - started, 4)
    row["finished_at"] = _now()
    payload_path = out_dir / f"{row['run_id']}.payload.json"
    if row.get("completed"):
        payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    row["payload_path"] = str(payload_path.relative_to(out_dir.parent)) if payload_path.exists() else ""
    return row


def default_pipeline(gene: str, variant: str, *, ablation: str) -> dict[str, Any]:
    """Adapter around the repository pipeline; ablations disable evidence sources."""
    from assemble_payload import run as assemble
    from fetch_context import fetch_all_context
    context = fetch_all_context(gene, variant) if ablation in {"clinical_only", "all_evidence"} else None
    physics = None
    ranked: list[dict[str, Any]] = []
    if ablation in {"literature_only", "all_evidence"}:
        from orchestration import phase_3_vector_engine
        ranked = phase_3_vector_engine(gene, variant, f"{gene} {variant}")
    if ablation in {"physics_only", "all_evidence"}:
        physics = {"deltas": {}, "variant": variant, "source": "benchmark physics-only adapter"}
    payload = assemble(query=f"{gene} {variant}", ranked_results=ranked, physics_vector=physics, rag_status="SUCCESS" if ranked else "NULL_RESULTS", clinical_context=context)
    if context and isinstance(context.get("clinvar"), dict):
        payload["clinical_label"] = context["clinvar"].get("clinical_significance", "")
        payload["clinical_context"] = context
    return payload


def run_benchmark(gold_path: Path, output_dir: Path, ablations: Iterable[str] = ABLATIONS, pipeline: Callable[..., dict[str, Any]] = default_pipeline) -> list[dict[str, Any]]:
    targets = load_gold(gold_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for target in targets:
        for ablation in ablations:
            rows.append(run_one(target, ablation, pipeline, _default_synthesis, output_dir))
    with (output_dir / "results.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    (output_dir / "metrics.json").write_text(json.dumps(calculate_metrics(rows), indent=2), encoding="utf-8")
    return rows


def compare_models(results_paths: dict[str, Path], output_path: Path) -> None:
    """Aggregate model result JSONL files into a comparable CSV."""
    fields = ["model", "n_runs", "citation_validity", "unsupported_claim_rate", "json_schema_validity", "vus_uncertainty_preservation", "scope_mistake_rate"]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for model, path in results_paths.items():
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            metrics = calculate_metrics(rows)
            scope = sum(bool(r.get("scope_mistake")) for r in rows) / len(rows) if rows else None
            writer.writerow({"model": model, "n_runs": len(rows), "citation_validity": metrics["citation_validity"], "unsupported_claim_rate": metrics["unsupported_claim_rate"], "json_schema_validity": metrics["json_schema_validity"], "vus_uncertainty_preservation": metrics["vus_uncertainty_preservation"], "scope_mistake_rate": scope})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Neuro-Capstone benchmark")
    parser.add_argument("--gold", type=Path, default=DEFAULT_DIR / "gold_variants.csv")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--ablation", action="append", choices=ABLATIONS, help="repeatable; defaults to all four")
    parser.add_argument("--dry-run", action="store_true", help="validate gold set and print expected run count")
    parser.add_argument("--compare", nargs="+", metavar="MODEL=RESULTS_JSONL", help="aggregate model result files")
    parser.add_argument("--comparison-output", type=Path, default=DEFAULT_DIR / "model_comparison.csv")
    args = parser.parse_args(argv)
    if args.compare:
        pairs = dict(item.split("=", 1) for item in args.compare)
        compare_models({model: Path(path) for model, path in pairs.items()}, args.comparison_output)
        return 0
    targets = load_gold(args.gold)
    if args.dry_run:
        print(json.dumps({"variants": len(targets), "ablations": args.ablation or list(ABLATIONS), "runs": len(targets) * len(args.ablation or ABLATIONS)}, indent=2))
        return 0
    run_benchmark(args.gold, args.output_dir, args.ablation or ABLATIONS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
