"""Blinded rescue-set evaluation using precomputed structure-only scores.

Input CSV columns:
gene,variant,label,alphamissense_score,structure_only_score

Only the two numeric score columns are used as predictors.
ClinVar labels are used exclusively as evaluation targets.
"""

import argparse
import csv
import json
import random
from pathlib import Path

from sklearn.metrics import roc_auc_score


def load_rows(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    if not rows:
        raise ValueError("Input CSV is empty.")

    required = {
        "gene", "variant", "label",
        "alphamissense_score", "structure_only_score",
    }
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    parsed = []
    seen = set()

    for line, row in enumerate(rows, start=2):
        label = row["label"].strip().lower()
        if label not in {"pathogenic", "benign"}:
            raise ValueError(
                f"Line {line}: label must be pathogenic or benign, got {label!r}"
            )

        identity = (row["gene"].strip(), row["variant"].strip())
        if identity in seen:
            raise ValueError(f"Duplicate variant: {identity}")
        seen.add(identity)

        try:
            am = float(row["alphamissense_score"])
            structure = float(row["structure_only_score"])
        except (TypeError, ValueError):
            raise ValueError(f"Line {line}: missing or invalid numeric score.")

        if not (0 <= am <= 1):
            raise ValueError(f"Line {line}: AlphaMissense score must be in [0, 1].")

        parsed.append({
            "gene": identity[0],
            "variant": identity[1],
            "label": 1 if label == "pathogenic" else 0,
            "alphamissense_score": am,
            "structure_only_score": structure,
        })

    labels = [r["label"] for r in parsed]
    if len(set(labels)) != 2:
        raise ValueError("AUROC requires both pathogenic and benign variants.")

    return parsed


def stratified_bootstrap_auc(labels, scores, iterations, seed):
    rng = random.Random(seed)
    positive = [i for i, label in enumerate(labels) if label == 1]
    negative = [i for i, label in enumerate(labels) if label == 0]

    values = []
    for _ in range(iterations):
        sample = (
            [rng.choice(positive) for _ in positive]
            + [rng.choice(negative) for _ in negative]
        )
        y = [labels[i] for i in sample]
        s = [scores[i] for i in sample]
        values.append(roc_auc_score(y, s))

    values.sort()
    lower = values[int(0.025 * iterations)]
    upper = values[min(int(0.975 * iterations), iterations - 1)]
    return lower, upper


def evaluate(rows, am_low_cutoff, structure_positive_cutoff, iterations, seed):
    labels = [r["label"] for r in rows]
    structure_scores = [r["structure_only_score"] for r in rows]

    auc = roc_auc_score(labels, structure_scores)
    lower, upper = stratified_bootstrap_auc(
        labels, structure_scores, iterations, seed
    )

    low_am_pathogenic = [
        r for r in rows
        if r["label"] == 1 and r["alphamissense_score"] < am_low_cutoff
    ]
    rescued = [
        r for r in low_am_pathogenic
        if r["structure_only_score"] >= structure_positive_cutoff
    ]

    return {
        "n_variants": len(rows),
        "n_pathogenic": sum(labels),
        "n_benign": len(labels) - sum(labels),
        "structure_only_auroc": auc,
        "bootstrap_95_ci": [lower, upper],
        "bootstrap_iterations": iterations,
        "bootstrap_seed": seed,
        "alphamissense_low_cutoff": am_low_cutoff,
        "structure_positive_cutoff": structure_positive_cutoff,
        "low_alphamissense_pathogenic_count": len(low_am_pathogenic),
        "rescued_false_negative_count": len(rescued),
        "rescued_variants": [
            {"gene": r["gene"], "variant": r["variant"]}
            for r in rescued
        ],
        "feature_policy": (
            "Only structure_only_score is used for structure-only AUROC. "
            "AlphaMissense is used only to define the low-score rescue slice. "
            "Labels are evaluation targets, never predictors."
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--alphamissense-low-cutoff", type=float, required=True)
    parser.add_argument("--structure-positive-cutoff", type=float, required=True)
    parser.add_argument("--bootstrap-iterations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if not 0 <= args.alphamissense_low_cutoff <= 1:
        parser.error("AlphaMissense cutoff must be between 0 and 1.")
    if args.bootstrap_iterations < 100:
        parser.error("Use at least 100 bootstrap iterations.")

    rows = load_rows(args.input)
    result = evaluate(
        rows,
        args.alphamissense_low_cutoff,
        args.structure_positive_cutoff,
        args.bootstrap_iterations,
        args.seed,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"\nReport written to: {args.output}")


if __name__ == "__main__":
    main()
