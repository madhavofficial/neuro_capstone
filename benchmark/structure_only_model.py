"""Train and evaluate a structure-only classifier on blinded variant features.

Inputs are deliberately split:
* --features: JSON array produced from benchmark.feature_vector.build_feature_row
* --labels: independent gold CSV with gene,variant,label (P/LP and B/LB accepted)

ClinVar fields are rejected in feature rows. Labels are joined only after feature
validation and are used only as targets. Evaluation uses out-of-fold predictions
with gene-grouped stratified CV to reduce within-gene leakage.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
from pathlib import Path
from typing import Any

import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
STRUCTURAL_KEYS = (
    "exposure", "sasa", "secondary_structure", "plddt_confidence",
    "delta_volume", "delta_hydrophobicity", "delta_charge", "backbone_strain",
    "salt_bridges_lost", "disulfides_lost", "h_bonds_lost_est",
    "interface_contacts_lost", "delta_aggregation", "monomer_ddg",
)
CATEGORICAL_KEYS = ("exposure", "secondary_structure", "backbone_strain")
LIST_COUNT_KEYS = ("salt_bridges_lost", "disulfides_lost")
NUMERIC_KEYS = tuple(
    key for key in STRUCTURAL_KEYS
    if key not in CATEGORICAL_KEYS and key not in LIST_COUNT_KEYS
)
FORBIDDEN_KEYS = {
    "clinvar", "clinical_label", "clinical_significance",
    "clinical_classification", "review_status", "clinvar_variation_id",
}


def _contains_forbidden(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).strip().lower() in FORBIDDEN_KEYS or _contains_forbidden(child):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden(item) for item in value)
    return False


def _normalise_label(value: Any) -> int:
    text = str(value or "").strip().lower()
    if text in {"p", "lp", "pathogenic", "likely pathogenic"}:
        return 1
    if text in {"b", "lb", "benign", "likely benign"}:
        return 0
    raise ValueError(f"Unsupported gold label {value!r}; expected P/LP or B/LB.")


def load_inputs(features_path: Path, labels_path: Path) -> list[dict[str, Any]]:
    features = json.loads(features_path.read_text(encoding="utf-8-sig"))
    if isinstance(features, dict):
        features = features.get("variants", features.get("rows"))
    if not isinstance(features, list) or not features:
        raise ValueError("Feature JSON must be a non-empty array of feature rows.")

    with labels_path.open(newline="", encoding="utf-8-sig") as handle:
        labels = list(csv.DictReader(handle))
    if not labels:
        raise ValueError("Gold-label CSV is empty.")
    required_labels = {"gene", "variant", "label"}
    if not required_labels.issubset(labels[0]):
        raise ValueError(f"Gold CSV requires columns: {sorted(required_labels)}")

    label_map: dict[tuple[str, str], int] = {}
    for line, row in enumerate(labels, start=2):
        key = (str(row["gene"]).strip().upper(), str(row["variant"]).strip().upper())
        if not all(key):
            raise ValueError(f"Gold CSV line {line}: gene and variant are required.")
        if key in label_map:
            raise ValueError(f"Duplicate gold label for {key}.")
        label_map[key] = _normalise_label(row["label"])

    parsed: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(features, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Feature row {index} is not an object.")
        if _contains_forbidden(row):
            raise ValueError(f"Feature row {index} contains a forbidden clinical/ClinVar field.")
        key = (str(row.get("gene", "")).strip().upper(),
               str(row.get("variant", "")).strip().upper())
        if not all(key):
            raise ValueError(f"Feature row {index}: gene and variant are required.")
        if key in seen:
            raise ValueError(f"Duplicate feature row for {key}.")
        seen.add(key)
        if key not in label_map:
            raise ValueError(f"No independent gold label found for feature row {key}.")
        structural = row.get("structural_features")
        if not isinstance(structural, dict):
            raise ValueError(f"{key}: structural_features must be an object.")
        missing = set(STRUCTURAL_KEYS) - set(structural)
        if missing:
            raise ValueError(f"{key}: missing structural features {sorted(missing)}.")

        cooked: dict[str, Any] = {"gene": key[0], "variant": key[1], "label": label_map[key]}
        for name in CATEGORICAL_KEYS:
            value = structural.get(name)
            cooked[name] = None if value is None or str(value).strip() == "" else str(value)
        for name in LIST_COUNT_KEYS:
            value = structural.get(name)
            if value is None:
                cooked[name] = None
            elif isinstance(value, list):
                cooked[name] = float(len(value))
            else:
                raise ValueError(f"{key}: {name} must be a list or null.")
        for name in NUMERIC_KEYS:
            value = structural.get(name)
            if value is None or value == "":
                cooked[name] = math.nan
            else:
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    raise ValueError(f"{key}: {name} must be numeric or null.")
                if not math.isfinite(number):
                    raise ValueError(f"{key}: {name} must be finite.")
                cooked[name] = number

        am = row.get("alphamissense_score")
        if am is None or am == "":
            cooked["alphamissense_score"] = None
        else:
            try:
                am = float(am)
            except (TypeError, ValueError):
                raise ValueError(f"{key}: AlphaMissense score must be numeric or null.")
            if not math.isfinite(am) or not 0 <= am <= 1:
                raise ValueError(f"{key}: AlphaMissense score must be finite and in [0, 1].")
            cooked["alphamissense_score"] = am
        parsed.append(cooked)

    if len({row["label"] for row in parsed}) != 2:
        raise ValueError("The matched feature set must contain both pathogenic and benign variants.")
    return parsed


def _make_model() -> Pipeline:
    numeric = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])
    prep = ColumnTransformer([
        ("numeric", numeric, list(NUMERIC_KEYS) + list(LIST_COUNT_KEYS)),
        ("categorical", categorical, list(CATEGORICAL_KEYS)),
    ])
    return Pipeline([
        ("preprocess", prep),
        ("classifier", LogisticRegression(class_weight="balanced", max_iter=3000, random_state=42)),
    ])


def _bootstrap_auc(labels: list[int], scores: list[float], iterations: int, seed: int) -> list[float]:
    rng = random.Random(seed)
    pos = [i for i, y in enumerate(labels) if y == 1]
    neg = [i for i, y in enumerate(labels) if y == 0]
    if min(len(pos), len(neg)) < 2:
        raise ValueError("At least two variants per class are required for a bootstrap CI.")
    values = []
    for _ in range(iterations):
        sample = [rng.choice(pos) for _ in pos] + [rng.choice(neg) for _ in neg]
        values.append(float(roc_auc_score([labels[i] for i in sample],
                                          [scores[i] for i in sample])))
    values.sort()
    return [values[int(0.025 * iterations)],
            values[min(int(0.975 * iterations), iterations - 1)]]


def evaluate(rows: list[dict[str, Any]], *, folds: int, iterations: int,
             seed: int, am_low_cutoff: float, structure_positive_cutoff: float) -> dict[str, Any]:
    labels = [row["label"] for row in rows]
    genes = [row["gene"] for row in rows]
    if len(set(genes)) < folds:
        raise ValueError(f"Gene-grouped {folds}-fold CV needs at least {folds} distinct genes.")
    splitter = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed)
    predictions = [math.nan] * len(rows)
    fold_summary = []
    x_rows = [{key: row[key] for key in NUMERIC_KEYS + LIST_COUNT_KEYS + CATEGORICAL_KEYS}
              for row in rows]
    for fold, (train, test) in enumerate(splitter.split(x_rows, labels, groups=genes), start=1):
        y_train = [labels[i] for i in train]
        y_test = [labels[i] for i in test]
        if len(set(y_train)) != 2 or len(set(y_test)) != 2:
            raise ValueError(
                f"Fold {fold} lacks one class in train or test. "
                "Reduce --folds or obtain a better class-by-gene distribution."
            )
        model = _make_model()
        model.fit(pd.DataFrame([x_rows[i] for i in train]), y_train)
        scores = model.predict_proba(pd.DataFrame([x_rows[i] for i in test]))[:, 1]
        for index, score in zip(test, scores):
            predictions[index] = float(score)
        fold_summary.append({
            "fold": fold,
            "train_variants": len(train),
            "test_variants": len(test),
            "test_genes": sorted({genes[i] for i in test}),
        })

    if any(not math.isfinite(score) for score in predictions):
        raise RuntimeError("Cross-validation did not produce an out-of-fold score for every row.")
    auc = float(roc_auc_score(labels, predictions))
    ci = _bootstrap_auc(labels, predictions, iterations, seed)
    rescue_candidates = [
        row for row in rows
        if row["label"] == 1
        and row["alphamissense_score"] is not None
        and row["alphamissense_score"] < am_low_cutoff
    ]
    by_key = {(row["gene"], row["variant"]): predictions[i] for i, row in enumerate(rows)}
    rescued = [
        row for row in rescue_candidates
        if by_key[(row["gene"], row["variant"])] >= structure_positive_cutoff
    ]
    return {
        "method": "LogisticRegression(class_weight=balanced) on structural features only; "
                  "gene-grouped StratifiedGroupKFold out-of-fold predictions",
        "n_variants": len(rows),
        "n_pathogenic": sum(labels),
        "n_benign": len(labels) - sum(labels),
        "n_genes": len(set(genes)),
        "structure_only_auroc_oof": auc,
        "bootstrap_95_ci": ci,
        "bootstrap_iterations": iterations,
        "bootstrap_seed": seed,
        "cv_folds": folds,
        "cv_folds_detail": fold_summary,
        "alphamissense_low_cutoff": am_low_cutoff,
        "structure_positive_cutoff": structure_positive_cutoff,
        "n_missing_alphamissense": sum(r["alphamissense_score"] is None for r in rows),
        "low_alphamissense_pathogenic_count": len(rescue_candidates),
        "rescued_false_negative_count": len(rescued),
        "rescued_variants": [
            {"gene": row["gene"], "variant": row["variant"],
             "structure_only_oof_score": by_key[(row["gene"], row["variant"])]}
            for row in rescued
        ],
        "feature_policy": "ClinVar/clinical fields and all labels are excluded from predictors. "
                          "AlphaMissense is used only to define the rescue slice; it is not a model feature.",
        "out_of_fold_predictions": [
            {"gene": row["gene"], "variant": row["variant"], "label": row["label"],
             "structure_only_oof_score": predictions[i]}
            for i, row in enumerate(rows)
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, required=True,
                        help="JSON array of build_feature_row outputs.")
    parser.add_argument("--labels", type=Path, required=True,
                        help="Independent gold CSV: gene,variant,label (P/LP/B/LB).")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--bootstrap-iterations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--alphamissense-low-cutoff", type=float, required=True)
    parser.add_argument("--structure-positive-cutoff", type=float, default=0.5)
    args = parser.parse_args()
    if args.folds < 2:
        parser.error("--folds must be at least 2.")
    if args.bootstrap_iterations < 100:
        parser.error("Use at least 100 bootstrap iterations.")
    if not 0 <= args.alphamissense_low_cutoff <= 1:
        parser.error("AlphaMissense cutoff must be in [0, 1].")
    if not 0 <= args.structure_positive_cutoff <= 1:
        parser.error("Structure positive cutoff must be in [0, 1].")

    rows = load_inputs(args.features, args.labels)
    result = evaluate(
        rows, folds=args.folds, iterations=args.bootstrap_iterations,
        seed=args.seed, am_low_cutoff=args.alphamissense_low_cutoff,
        structure_positive_cutoff=args.structure_positive_cutoff,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items()
                      if k != "out_of_fold_predictions"}, indent=2))
    print(f"\nFull report written to: {args.output}")


if __name__ == "__main__":
    main()
