"""Train and evaluate a structure-only classifier on blinded variant features.

Predictors and labels are deliberately separate. Clinical/ClinVar fields are
rejected from feature JSON; AlphaMissense is used only to define the rescue
slice. Validation is gene-grouped and uncertainty is estimated by resampling
whole gene clusters rather than treating correlated variants as independent.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

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
MODEL_KEYS = NUMERIC_KEYS + LIST_COUNT_KEYS + CATEGORICAL_KEYS
FORBIDDEN_KEYS = {
    "clinvar", "clinical_label", "clinical_significance",
    "clinical_classification", "review_status", "clinvar_variation_id",
}


def _contains_forbidden(value: Any) -> bool:
    if isinstance(value, dict):
        return any(str(k).strip().lower() in FORBIDDEN_KEYS or _contains_forbidden(v)
                   for k, v in value.items())
    if isinstance(value, list):
        return any(_contains_forbidden(item) for item in value)
    return False


def _normalise_label(value: Any) -> int:
    text = str(value or "").strip().lower()
    if text in {"p", "lp", "pathogenic", "likely pathogenic"}:
        return 1
    if text in {"b", "lb", "benign", "likely benign"}:
        return 0
    raise ValueError(f"Unsupported gold label {value!r}; expected P/LP or B/LB.")


def _numeric_value(value: Any, *, key: tuple[str, str], name: str) -> float:
    if value is None or value == "":
        return math.nan
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key}: {name} must be numeric or null.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{key}: {name} must be finite.")
    if name in {"sasa", "h_bonds_lost_est", "interface_contacts_lost"} and number < 0:
        raise ValueError(f"{key}: {name} cannot be negative.")
    if name == "plddt_confidence" and not 0 <= number <= 100:
        raise ValueError(f"{key}: plddt_confidence must be in [0, 100].")
    return number


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
    required = {"gene", "variant", "label"}
    if not required.issubset(labels[0]):
        raise ValueError(f"Gold CSV requires columns: {sorted(required)}")

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

        cooked: dict[str, Any] = {"gene": key[0], "variant": key[1],
                                  "label": label_map[key]}
        for name in CATEGORICAL_KEYS:
            value = structural.get(name)
            cooked[name] = None if value is None or str(value).strip() == "" else str(value)
        for name in LIST_COUNT_KEYS:
            value = structural.get(name)
            if value is None:
                cooked[name] = math.nan
            elif isinstance(value, list):
                cooked[name] = float(len(value))
            else:
                raise ValueError(f"{key}: {name} must be a list or null.")
        for name in NUMERIC_KEYS:
            cooked[name] = _numeric_value(structural.get(name), key=key, name=name)

        am = row.get("alphamissense_score")
        if am is None or am == "":
            cooked["alphamissense_score"] = None
        else:
            try:
                am = float(am)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key}: AlphaMissense score must be numeric or null.") from exc
            if not math.isfinite(am) or not 0 <= am <= 1:
                raise ValueError(f"{key}: AlphaMissense score must be finite and in [0, 1].")
            cooked["alphamissense_score"] = am
        parsed.append(cooked)

    if len({row["label"] for row in parsed}) != 2:
        raise ValueError("The matched feature set must contain both pathogenic and benign variants.")
    return parsed


def _make_model(training_frame: pd.DataFrame) -> Pipeline:
    # Drop columns that are entirely missing in this training fold. This avoids
    # sklearn's all-empty-feature warnings and prevents test-fold information
    # from deciding which predictors are retained.
    numeric = [k for k in NUMERIC_KEYS + LIST_COUNT_KEYS
               if not training_frame[k].isna().all()]
    categorical = [k for k in CATEGORICAL_KEYS
                   if not training_frame[k].isna().all()]
    if not numeric and not categorical:
        raise ValueError("No structural predictors are observed in this training fold.")

    transformers = []
    if numeric:
        transformers.append(("numeric", Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]), numeric))
    if categorical:
        transformers.append(("categorical", Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]), categorical))
    prep = ColumnTransformer(transformers, remainder="drop")
    return Pipeline([
        ("preprocess", prep),
        ("classifier", LogisticRegression(class_weight="balanced",
                                          max_iter=3000, random_state=42)),
    ])


def _cluster_bootstrap_auc(labels: list[int], scores: list[float],
                           genes: list[str], iterations: int,
                           seed: int) -> tuple[list[float], dict[str, int]]:
    """Stratified cluster bootstrap: resample whole genes within label-profile strata.

    Genes are stratified as pathogenic-only, benign-only, or mixed. Keeping
    each stratum's gene count fixed preserves both classes while resampling
    clusters, not individual variants.
    """
    by_gene: dict[str, list[int]] = defaultdict(list)
    for index, gene in enumerate(genes):
        by_gene[gene].append(index)
    strata: dict[tuple[int, ...], list[str]] = defaultdict(list)
    for gene, indices in by_gene.items():
        profile = tuple(sorted({labels[i] for i in indices}))
        strata[profile].append(gene)
    if len(by_gene) < 2:
        raise ValueError("At least two distinct genes are required for a cluster bootstrap.")

    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(iterations):
        sampled_indices: list[int] = []
        for members in strata.values():
            for _draw in members:
                sampled_gene = rng.choice(members)
                sampled_indices.extend(by_gene[sampled_gene])
        sample_labels = [labels[i] for i in sampled_indices]
        if len(set(sample_labels)) != 2:
            continue
        sample_scores = [scores[i] for i in sampled_indices]
        values.append(float(roc_auc_score(sample_labels, sample_scores)))
    if len(values) < max(100, int(iterations * 0.8)):
        raise ValueError(
            f"Only {len(values)}/{iterations} valid gene-cluster bootstrap samples; "
            "the dataset has insufficient class diversity across genes."
        )
    values.sort()
    ci = [values[int(0.025 * len(values))],
          values[min(int(0.975 * len(values)), len(values) - 1)]]
    return ci, {"requested": iterations, "valid": len(values),
                "invalid": iterations - len(values), "genes": len(by_gene)}


def evaluate(rows: list[dict[str, Any]], *, folds: int, iterations: int,
             seed: int, am_low_cutoff: float,
             structure_positive_cutoff: float) -> dict[str, Any]:
    labels = [row["label"] for row in rows]
    genes = [row["gene"] for row in rows]
    if len(set(genes)) < folds:
        raise ValueError(f"Gene-grouped {folds}-fold CV needs at least {folds} distinct genes.")
    splitter = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed)
    predictions = [math.nan] * len(rows)
    fold_summary = []
    x_rows = [{key: row[key] for key in MODEL_KEYS} for row in rows]
    for fold, (train, test) in enumerate(
            splitter.split(x_rows, labels, groups=genes), start=1):
        y_train = [labels[i] for i in train]
        y_test = [labels[i] for i in test]
        if len(set(y_train)) != 2 or len(set(y_test)) != 2:
            raise ValueError(
                f"Fold {fold} lacks one class in train or test. "
                "Reduce --folds or obtain a better class-by-gene distribution."
            )
        train_frame = pd.DataFrame([x_rows[i] for i in train])
        test_frame = pd.DataFrame([x_rows[i] for i in test])
        model = _make_model(train_frame)
        model.fit(train_frame, y_train)
        scores = model.predict_proba(test_frame)[:, 1]
        for index, score in zip(test, scores):
            predictions[index] = float(score)
        fold_summary.append({
            "fold": fold, "train_variants": len(train), "test_variants": len(test),
            "test_genes": sorted({genes[i] for i in test}),
            "dropped_all_missing_features": [
                key for key in MODEL_KEYS if train_frame[key].isna().all()
            ],
        })

    if any(not math.isfinite(score) for score in predictions):
        raise RuntimeError("Cross-validation did not produce an out-of-fold score for every row.")
    auc = float(roc_auc_score(labels, predictions))
    ci, bootstrap = _cluster_bootstrap_auc(labels, predictions, genes, iterations, seed)
    rescue_candidates = [
        row for row in rows if row["label"] == 1
        and row["alphamissense_score"] is not None
        and row["alphamissense_score"] < am_low_cutoff
    ]
    by_key = {(row["gene"], row["variant"]): predictions[i]
              for i, row in enumerate(rows)}
    rescued = [row for row in rescue_candidates
               if by_key[(row["gene"], row["variant"])] >= structure_positive_cutoff]
    missingness = {
        key: sum(pd.isna(row[key]) for row in x_rows)
        for key in MODEL_KEYS
    }
    return {
        "method": "Balanced logistic regression on structural features only; "
                  "gene-grouped StratifiedGroupKFold out-of-fold predictions",
        "n_variants": len(rows), "n_pathogenic": sum(labels),
        "n_benign": len(labels) - sum(labels), "n_genes": len(set(genes)),
        "structure_only_auroc_oof": auc, "bootstrap_95_ci_gene_cluster": ci,
        "bootstrap_method": "Stratified gene-cluster percentile bootstrap over OOF predictions",
        "bootstrap_iterations": bootstrap,
        "bootstrap_seed": seed, "cv_folds": folds, "cv_folds_detail": fold_summary,
        "feature_missingness_counts": missingness,
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
        "feature_policy": "Clinical/ClinVar fields and labels are excluded from predictors. "
                          "AlphaMissense defines the rescue slice only; it is not a model feature.",
        "uncertainty_note": "The gene-cluster bootstrap resamples genes within pathogenic-only, "
                            "benign-only, and mixed-label gene strata. The interval is conditional "
                            "on the out-of-fold predictions and does not capture model-selection uncertainty.",
        "out_of_fold_predictions": [
            {"gene": row["gene"], "variant": row["variant"], "label": row["label"],
             "structure_only_oof_score": predictions[i]}
            for i, row in enumerate(rows)
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
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
        parser.error("--bootstrap-iterations must be at least 100.")
    if not 0 <= args.alphamissense_low_cutoff <= 1:
        parser.error("AlphaMissense cutoff must be in [0, 1].")
    if not 0 <= args.structure_positive_cutoff <= 1:
        parser.error("Structure positive cutoff must be in [0, 1].")
    rows = load_inputs(args.features, args.labels)
    result = evaluate(rows, folds=args.folds, iterations=args.bootstrap_iterations,
                      seed=args.seed, am_low_cutoff=args.alphamissense_low_cutoff,
                      structure_positive_cutoff=args.structure_positive_cutoff)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items()
                      if k != "out_of_fold_predictions"}, indent=2))
    print(f"\nFull report written to: {args.output}")


if __name__ == "__main__":
    main()
