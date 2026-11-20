"""Batch-export blinded feature rows from full_runner run directories.

Expected layout:
  <runs-root>/<run-id>/analysis/<GENE>_<VARIANT>_physics.json
  <runs-root>/<run-id>/payload.json

Feature JSON contains no labels or clinical fields. The separate audit CSV
records gold labels and per-variant export status.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from benchmark.feature_vector import build_feature_row


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
    accepted = {"P", "LP", "B", "LB", "PATHOGENIC", "LIKELY PATHOGENIC",
                "BENIGN", "LIKELY BENIGN"}
    for line, row in enumerate(rows, start=2):
        key = (row["gene"].strip().upper(), row["variant"].strip().upper())
        label = row["label"].strip().upper()
        if not all(key) or label not in accepted:
            raise ValueError(f"Gold CSV line {line}: invalid identity or non-binary label.")
        if key in result:
            raise ValueError(f"Duplicate gold variant {key}.")
        result[key] = label
    if len({label in {"P", "LP", "PATHOGENIC", "LIKELY PATHOGENIC"}
            for label in result.values()}) != 2:
        raise ValueError("Gold CSV must contain both pathogenic and benign labels.")
    return result


def export_batch(runs_root: Path, labels_csv: Path, features_out: Path,
                 audit_out: Path, *, require_alphamissense: bool = False) -> dict[str, Any]:
    if not runs_root.is_dir():
        raise FileNotFoundError(f"Runs directory does not exist: {runs_root}")
    labels = _gold_labels(labels_csv)
    candidates: dict[tuple[str, str], list[Path]] = {}
    for physics in runs_root.glob("*/analysis/*_physics.json"):
        try:
            key = _variant_from_physics(physics)
        except ValueError:
            continue
        if key in labels:
            candidates.setdefault(key, []).append(physics)

    exported, audit = [], []
    missing_physics, missing_am, missing_payload = [], [], []
    errors, duplicate_runs_collapsed = [], 0
    for key in sorted(labels):
        paths = candidates.get(key, [])
        if not paths:
            missing_physics.append(key)
            audit.append({"gene": key[0], "variant": key[1],
                          "label": labels[key], "status": "missing_physics"})
            continue
        duplicate_runs_collapsed += max(0, len(paths) - 1)

        def run_rank(physics: Path) -> tuple[int, float, float]:
            run_dir = physics.parent.parent
            payload_path = run_dir / "payload.json"
            has_alpha, payload_mtime = 0, 0.0
            if payload_path.exists():
                try:
                    payload = _load_json(payload_path)
                    clinical = payload.get("clinical_context")
                    if not isinstance(clinical, dict):
                        clinical = payload
                    block = clinical.get("alphamissense_sniper")
                    has_alpha = int(isinstance(block, dict) and block.get("score") is not None)
                    payload_mtime = payload_path.stat().st_mtime
                except (OSError, ValueError, json.JSONDecodeError):
                    pass
            return has_alpha, payload_mtime, physics.stat().st_mtime

        ranked = sorted(paths, key=run_rank, reverse=True)
        chosen = None
        chosen_status = "exported"
        chosen_error = None
        for physics in ranked:
            candidate_status = "exported"
            run_dir = physics.parent.parent
            payload_path = run_dir / "payload.json"
            context = None
            if payload_path.exists():
                try:
                    payload = _load_json(payload_path)
                    context = payload.get("clinical_context")
                    if not isinstance(context, dict):
                        context = payload
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    chosen_error = f"{payload_path}: {exc}"
                    continue
            else:
                candidate_status = "exported_missing_payload"
            try:
                analysis = _load_json(physics)
                row = build_feature_row(key[0], key[1], analysis, context)
                chosen = row
                chosen_status = candidate_status
                break
            except Exception as exc:
                chosen_error = f"{physics}: {exc}"
        if chosen is None:
            errors.append({"gene": key[0], "variant": key[1],
                           "error": chosen_error or "no usable run"})
            audit.append({"gene": key[0], "variant": key[1],
                          "label": labels[key], "status": "feature_error"})
            continue

        if chosen_status == "exported_missing_payload":
            missing_payload.append(key)
        if chosen["alphamissense_score"] is None:
            missing_am.append(key)
            if require_alphamissense:
                audit.append({"gene": key[0], "variant": key[1],
                              "label": labels[key], "status": "missing_alphamissense"})
                continue
        exported.append(chosen)
        status = ("exported_missing_alphamissense"
                  if chosen["alphamissense_score"] is None else chosen_status)
        audit.append({"gene": key[0], "variant": key[1],
                      "label": labels[key], "status": status})

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
        "missing_payload": len(missing_payload),
        "missing_alphamissense": len(missing_am),
        "duplicate_runs_collapsed": duplicate_runs_collapsed,
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
