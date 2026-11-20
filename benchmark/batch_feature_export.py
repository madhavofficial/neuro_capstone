"""Batch-export blinded feature rows from existing full_runner outputs.

The predictor CSV deliberately contains no clinical labels or ClinVar identifiers.
A separate audit CSV records gold labels and source/review metadata for evaluation.
Existing run outputs are reused; this script does not rerun structure analysis.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmark.feature_vector import (  # noqa: E402
    STRUCTURAL_FEATURE_KEYS,
    build_feature_row,
)

DEFAULT_RUNS = ROOT / "data" / "benchmarks" / "runs"
DEFAULT_GOLD = ROOT / "data" / "benchmarks" / "gold_variants_issue2_draft.csv"
DEFAULT_FEATURES = ROOT / "data" / "benchmarks" / "issue2_feature_vectors.csv"
DEFAULT_AUDIT = ROOT / "data" / "benchmarks" / "issue2_feature_labels_audit.csv"
DEFAULT_REPORT = ROOT / "data" / "benchmarks" / "issue2_feature_export_report.json"

FEATURE_FIELDS = [
    "gene", "variant", "alphamissense_score",
    "exposure", "sasa", "secondary_structure", "plddt_confidence",
    "delta_volume", "delta_hydrophobicity", "delta_charge",
    "backbone_strain", "salt_bridges_lost_count", "disulfides_lost_count",
    "h_bonds_lost_est", "interface_contacts_lost", "delta_aggregation",
    "monomer_ddg", "source_run",
]
AUDIT_FIELDS = [
    "gene", "variant", "label", "label_source", "clinvar_variation_id",
    "review_status", "feature_status", "source_run",
]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _feature_csv_row(row: dict[str, Any], run_id: str) -> dict[str, Any]:
    features = row["structural_features"]
    return {
        "gene": row["gene"],
        "variant": row["variant"],
        "alphamissense_score": row["alphamissense_score"],
        "exposure": features.get("exposure"),
        "sasa": features.get("sasa"),
        "secondary_structure": features.get("secondary_structure"),
        "plddt_confidence": features.get("plddt_confidence"),
        "delta_volume": features.get("delta_volume"),
        "delta_hydrophobicity": features.get("delta_hydrophobicity"),
        "delta_charge": features.get("delta_charge"),
        "backbone_strain": features.get("backbone_strain"),
        "salt_bridges_lost_count": len(features.get("salt_bridges_lost") or []),
        "disulfides_lost_count": len(features.get("disulfides_lost") or []),
        "h_bonds_lost_est": features.get("h_bonds_lost_est"),
        "interface_contacts_lost": features.get("interface_contacts_lost"),
        "delta_aggregation": features.get("delta_aggregation"),
        "monomer_ddg": features.get("monomer_ddg"),
        "source_run": run_id,
    }


def _load_gold(path: Path, *, strict_review: bool = True) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    required = {"gene", "variant", "label"}
    if not rows:
        raise ValueError(f"Gold-set CSV is empty: {path}")
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"Gold-set CSV missing columns: {sorted(missing)}")

    accepted_review = {
        "practice guideline",
        "reviewed by expert panel",
        "criteria provided, multiple submitters, no conflicts",
    }
    selected = []
    for row in rows:
        label = row["label"].strip().lower()
        if label not in {"pathogenic", "benign"}:
            continue
        status = row.get("review_status", "").strip().lower()
        if strict_review and status not in accepted_review:
            continue
        selected.append(row)
    if not selected:
        raise ValueError(
            "No pathogenic/benign rows passed the gold-set filter. "
            "Use the strict ClinVar draft or explicitly pass --allow-non-strict-review."
        )
    return selected


def _index_run_outputs(runs_dir: Path) -> dict[tuple[str, str], list[tuple[Path, Path | None, str]]]:
    """Index physics JSONs by gene/variant and pair each with its run payload."""
    indexed: dict[tuple[str, str], list[tuple[Path, Path | None, str]]] = defaultdict(list)
    for analysis_path in sorted(runs_dir.glob("*/analysis/*_physics.json")):
        stem = analysis_path.stem.removesuffix("_physics")
        if "_" not in stem:
            continue
        gene, variant = stem.split("_", 1)
        payload_path = analysis_path.parent.parent / "payload.json"
        indexed[(gene.upper(), variant.upper())].append(
            (analysis_path, payload_path if payload_path.is_file() else None, analysis_path.parent.parent.name)
        )
    return indexed


def _candidate_quality(item: tuple[Path, Path | None, str]) -> tuple[int, int]:
    analysis_path, payload_path, _ = item
    has_payload = int(payload_path is not None)
    has_am = 0
    if payload_path is not None:
        try:
            payload = _read_json(payload_path)
            clinical = payload.get("clinical_context")
            if not isinstance(clinical, dict):
                clinical = {}
            am_block = clinical.get("alphamissense_sniper")
            has_am = int(isinstance(am_block, dict) and am_block.get("score") is not None)
        except (OSError, ValueError, TypeError):
            pass
    return has_am, has_payload


def export(
    gold_path: Path = DEFAULT_GOLD,
    runs_dir: Path = DEFAULT_RUNS,
    feature_path: Path = DEFAULT_FEATURES,
    audit_path: Path = DEFAULT_AUDIT,
    report_path: Path = DEFAULT_REPORT,
    *,
    strict_review: bool = True,
) -> dict[str, Any]:
    gold_rows = _load_gold(gold_path, strict_review=strict_review)
    run_index = _index_run_outputs(runs_dir)
    feature_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    missing_structure: list[str] = []
    missing_am: list[str] = []
    errors: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for gold in gold_rows:
        gene = gold["gene"].strip().upper()
        variant = gold["variant"].strip().upper()
        identity = (gene, variant)
        if identity in seen:
            raise ValueError(f"Duplicate gold variant: {gene} {variant}")
        seen.add(identity)
        candidates = run_index.get(identity, [])
        if not candidates:
            missing_structure.append(f"{gene} {variant}")
            audit_rows.append({
                "gene": gene, "variant": variant, "label": gold["label"],
                "label_source": gold.get("label_source", ""),
                "clinvar_variation_id": gold.get("clinvar_variation_id", ""),
                "review_status": gold.get("review_status", ""),
                "feature_status": "missing_structure", "source_run": "",
            })
            continue

        # Prefer an existing run with AlphaMissense, then any run with payload.
        chosen = max(candidates, key=_candidate_quality)
        analysis_path, payload_path, run_id = chosen
        try:
            analysis = _read_json(analysis_path)
            payload = _read_json(payload_path) if payload_path else {}
            clinical = payload.get("clinical_context")
            if not isinstance(clinical, dict):
                clinical = {}
            built = build_feature_row(gene, variant, analysis, clinical)
            flat = _feature_csv_row(built, run_id)
            feature_rows.append(flat)
            status = "exported"
            if built["alphamissense_score"] is None:
                status = "missing_alphamissense"
                missing_am.append(f"{gene} {variant}")
            audit_rows.append({
                "gene": gene, "variant": variant, "label": gold["label"],
                "label_source": gold.get("label_source", ""),
                "clinvar_variation_id": gold.get("clinvar_variation_id", ""),
                "review_status": gold.get("review_status", ""),
                "feature_status": status, "source_run": run_id,
            })
        except Exception as exc:
            errors.append({"variant": f"{gene} {variant}", "error": f"{type(exc).__name__}: {exc}"})
            audit_rows.append({
                "gene": gene, "variant": variant, "label": gold["label"],
                "label_source": gold.get("label_source", ""),
                "clinvar_variation_id": gold.get("clinvar_variation_id", ""),
                "review_status": gold.get("review_status", ""),
                "feature_status": "export_error", "source_run": run_id,
            })

    feature_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with feature_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FEATURE_FIELDS)
        writer.writeheader()
        writer.writerows(feature_rows)
    with audit_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUDIT_FIELDS)
        writer.writeheader()
        writer.writerows(audit_rows)

    report = {
        "gold_input": str(gold_path),
        "runs_directory": str(runs_dir),
        "strict_review_filter": strict_review,
        "accepted_gold_variants": len(gold_rows),
        "feature_rows_exported": len(feature_rows),
        "rows_with_alphamissense": sum(r["alphamissense_score"] is not None for r in feature_rows),
        "rows_missing_alphamissense": missing_am,
        "variants_missing_structure": missing_structure,
        "export_errors": errors,
        "predictor_file": str(feature_path),
        "label_audit_file": str(audit_path),
        "leakage_policy": (
            "Predictor CSV contains only gene/variant identifiers, AlphaMissense score, "
            "and structural features. Labels, ClinVar IDs, review status, and label sources "
            "are written only to the separate audit file."
        ),
        "structural_feature_keys": list(STRUCTURAL_FEATURE_KEYS),
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--features-out", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--audit-out", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--allow-non-strict-review",
        action="store_true",
        help="Include pathogenic/benign rows even if their ClinVar review status is below the strict accepted set.",
    )
    args = parser.parse_args(argv)
    report = export(
        args.gold, args.runs_dir, args.features_out, args.audit_out, args.report_out,
        strict_review=not args.allow_non_strict_review,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
