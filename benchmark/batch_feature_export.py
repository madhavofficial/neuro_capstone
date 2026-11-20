"""Batch-export blinded feature rows from full_runner run directories.

Expected run layout:
  <runs-root>/<run-id>/analysis/<GENE>_<VARIANT>_physics.json
  <runs-root>/<run-id>/payload.json

The output feature JSON contains only gene, variant, AlphaMissense score, and
structural_features. Independent labels are validated against the supplied
gold CSV but are written to a separate audit CSV, never into predictor JSON.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from benchmark.feature_vector import build_feature_row, STRUCTURAL_FEATURE_KEYS


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _variant_from_physics(path: Path) -> tuple[str, str]:
    stem = path.name.removesuffix("_physics.json")
    if "_" not in stem:
        raise ValueError(f"Cannot parse GENE_VARIANT from {path.name}")
    gene, variant = stem.split("_", 1)
    if not gene or not variant:
        raise ValueError(f"Cannot parse GENE_VARIANT from {path.name}")
    return gene.upper(), variant.upper()


def _gold_labels(path: Path) -> dict[tuple[str, str], str]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or not {"gene", "variant", "label"}.issubset(rows[0]):
        raise ValueError("Gold CSV must contain gene,variant,label columns.")
    result: dict[tuple[str, str], str] = {}
    for line, row in enumerate(rows, start=2):
        key = (row["gene"].strip().upper(), row["variant"].strip().upper())
        label = row["label"].strip().upper()
        if not all(key) or label not in {"P", "LP", "B", "LB", "PATHOGENIC", "LIKELY PATHOGENIC", "BENIGN", "LIKELY BENIGN"}:
            raise ValueError(f"Gold CSV line {line}: invalid identity or non-binary label.")
        if key in result:
            raise ValueError(f"Duplicate gold variant {key}.")
        result[key] = label
    return result


def export_batch(runs_root: Path, labels_csv: Path, features_out: Path,
                 audit_out: Path, *, require_alphamissense: bool = False) -> dict[str, Any]:
    labels = _gold_labels(labels_csv)
    candidates: dict[tuple[str, str], list[Path]] = {}
    for physics in runs_root.glob("*/analysis/*_physics.json"):
        key = _variant_from_physics(physics)
        if key in labels:
            candidates.setdefault(key, []).append(physics)

    exported = []
    audit = []
    missing_physics = []
    missing_context = []
    missing_am = []
    errors = []
    for key in sorted(labels):
        paths = candidates.get(key, [])
        if not paths:
            missing_physics.append(key)
            audit.append({"gene": key[0], "variant": key[1], "label": labels[key], "status": "missing_physics"})
            continue
        # Prefer a run with a payload containing AlphaMissense, then newest
        # modification time. Duplicate runs are not emitted as duplicate variants.
        def run_rank(physics: Path) -> tuple[int, float, float]:
            run_dir = physics.parent.parent
            payload_path = run_dir / "payload.json"
            has_alpha = 0
            payload_mtime = 0.0
            if payload_path.exists():
                try:
                    payload = _load_json(payload_path)
                    clinical = payload.get("clinical_context")
                    if not isinstance(clinical, dict):
                        clinical = payload
                    context_block = clinical.get("alphamissense_sniper") if isinstance(clinical, dict) else None
                    has_alpha = int(isinstance(context_block, dict) and context_block.get("score") is not None)
                    payload_mtime = payload_path.stat().st_mtime
                except Exception:
                    pass
            return (has_alpha, payload_mtime, physics.stat().st_mtime)

        ranked = sorted(paths, key=run_rank, reverse=True)
        chosen = None
        chosen_context = None
        chosen_error = None
        for physics in ranked:
            run_dir = physics.parent.parent
            payload_path = run_dir / "payload.json"
            context = None
            if payload_path.exists():
                try:
                    payload = _load_json(payload_path)
                    context = payload.get("clinical_context")
                    if not isinstance(context, dict):
                        context = payload
                except Exception as exc:
                    chosen_error = f"{payload_path}: {exc}"
                    continue
            try:
                analysis = _load_json(physics)
                row = build_feature_row(key[0], key[1], analysis, context)
                chosen, chosen_context = row, context
                break
            except Exception as exc:
                chosen_error = f"{physics}: {exc}"
        if chosen is None:
            errors.append({"gene": key[0], "variant": key[1], "error": chosen_error or "no usable run"})
            audit.append({"gene": key[0], "variant": key[1], "label": labels[key], "status": "feature_error"})
            continue
        if chosen["alphamissense_score"] is None:
            missing_am.append(key)
            if require_alphamissense:
                audit.append({"gene": key[0], "variant": key[1], "label": labels[key], "status": "missing_alphamissense"})
                continue
        exported.append(chosen)
        audit.append({
            "gene": key[0], "variant": key[1], "label": labels[key],
            "status": "exported" if chosen["alphamissense_score"] is not None else "exported_missing_alphamissense",
        })

    features_out.parent.mkdir(parents=True, exist_ok=True)
    audit_out.parent.mkdir(parents=True, exist_ok=True)
    features_out.write_text(json.dumps(exported, indent=2), encoding="utf-8")
    with audit_out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["gene", "variant", "label", "status"])
        writer.writeheader()
        writer.writerows(audit)
    return {
        "gold_variants": len(labels),
        "feature_rows_exported": len(exported),
        "missing_physics": len(missing_physics),
        "missing_alphamissense": len(missing_am),
        "feature_errors": len(errors),
        "features_json": str(features_out),
        "label_audit_csv_separate_from_features": str(audit_out),
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--features-out", type=Path, required=True)
    parser.add_argument("--audit-out", type=Path, required=True)
    parser.add_argument("--require-alphamissense", action="store_true")
    args = parser.parse_args()
    result = export_batch(args.runs_root, args.labels, args.features_out,
                          args.audit_out, require_alphamissense=args.require_alphamissense)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
