"""Export the blinded structural feature vector on the S669 direct set.

Each row is a virtual substitution on the wild-type PDB. AlphaMissense is not
attached: S669 rows are PDB chains with experimental folding ΔΔG, not clinical
variants. Guessed gained contacts are not written.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analyze_structure import analyze_protein  # noqa: E402
from benchmark.feature_vector import structural_features  # noqa: E402
from benchmark.s669_runner import (  # noqa: E402
    DEFAULT_OUT_DIR,
    DEFAULT_PDB_DIR,
    DEFAULT_VARIANTS,
    _residue_status,
    collapse_stability_score,
    load_variants,
    pearson,
    spearman,
    write_first_model,
)

NUMERIC_FEATURES = (
    "sasa",
    "plddt_confidence",
    "delta_volume",
    "delta_hydrophobicity",
    "delta_charge",
    "salt_bridges_lost",
    "disulfides_lost",
    "h_bonds_lost_est",
    "backbone_strain_flag",
    "interface_contacts_lost",
    "delta_aggregation",
    "heuristic_score",
)

FIELDNAMES = [
    "pdb",
    "chain",
    "variant",
    "wt",
    "position",
    "mut",
    "ddg",
    "status",
    "exposure",
    "sasa",
    "secondary_structure",
    "plddt_confidence",
    "delta_volume",
    "delta_hydrophobicity",
    "delta_charge",
    "backbone_strain",
    "backbone_strain_flag",
    "salt_bridges_lost",
    "disulfides_lost",
    "h_bonds_lost_est",
    "interface_contacts_lost",
    "delta_aggregation",
    "heuristic_score",
]


def _blank(row: dict[str, Any], status: str, detail: str = "") -> dict[str, Any]:
    record = {
        "pdb": row["pdb"],
        "chain": row["chain"],
        "variant": f"{row['wt']}{row['position']}{row['mut']}",
        "wt": row["wt"],
        "position": row["position"],
        "mut": row["mut"],
        "ddg": row["ddg"],
        "status": status,
    }
    for key in FIELDNAMES:
        record.setdefault(key, "")
    if detail:
        record["detail"] = detail
    return record


def score_pdb_group(task: dict[str, Any]) -> list[dict[str, Any]]:
    """Build one feature row for every variant on one wild-type PDB."""
    pdb_path = task["pdb_path"]
    scored: list[dict[str, Any]] = []
    for row in task["rows"]:
        try:
            status = _residue_status(pdb_path, row)
            if status != "ok":
                scored.append(_blank(row, status))
                continue
            variant = f"{row['wt']}{row['position']}{row['mut']}"
            analysis = analyze_protein(pdb_path, variant, chain_id=row["chain"], verbose=False)
            if not analysis:
                scored.append(_blank(row, "analysis_failed"))
                continue
            features = structural_features(analysis)
            record = _blank(row, "scored")
            record.update(
                {
                    "exposure": features["exposure"],
                    "sasa": features["sasa"],
                    "secondary_structure": features["secondary_structure"],
                    "plddt_confidence": features["plddt_confidence"],
                    "delta_volume": features["delta_volume"],
                    "delta_hydrophobicity": features["delta_hydrophobicity"],
                    "delta_charge": features["delta_charge"],
                    "backbone_strain": features["backbone_strain"],
                    "backbone_strain_flag": 0 if features["backbone_strain"] in (None, "None") else 1,
                    "salt_bridges_lost": len(features["salt_bridges_lost"]),
                    "disulfides_lost": len(features["disulfides_lost"]),
                    "h_bonds_lost_est": features["h_bonds_lost_est"],
                    "interface_contacts_lost": features["interface_contacts_lost"],
                    "delta_aggregation": features["delta_aggregation"],
                    "heuristic_score": f"{collapse_stability_score(analysis):.6f}",
                }
            )
            scored.append(record)
        except Exception as exc:
            scored.append(_blank(row, "analysis_failed", str(exc)))
    return scored


def _as_float(value: Any) -> float:
    return float(value)


def correlate(rows: list[dict[str, Any]]) -> list[dict[str, float | str]]:
    results = []
    for name in NUMERIC_FEATURES:
        paired = [
            (_as_float(row[name]), _as_float(row["ddg"]))
            for row in rows
            if row.get(name) not in ("", None)
        ]
        if len(paired) < 3:
            results.append({"feature": name, "pearson": float("nan"), "spearman": float("nan")})
            continue
        observed, experimental = zip(*paired)
        results.append(
            {
                "feature": name,
                "pearson": pearson(list(observed), list(experimental)),
                "spearman": spearman(list(observed), list(experimental)),
            }
        )
    return results


def _format_r(value: float) -> str:
    if value != value:
        return "undefined"
    return f"{value:.3f}"


def render_report(rows: list[dict[str, Any]], correlations: list[dict[str, float | str]]) -> str:
    scored = [row for row in rows if row["status"] == "scored"]
    lines = [
        "# S669 feature-vector check",
        "",
        "Each row is the blinded structural feature vector from `benchmark/feature_vector.py`: "
        "wild-type exposure, SASA, secondary structure, B-factor, residue-table Δ volume, "
        "Δ hydrophobicity, and Δ charge, plus contacts measured on wild-type atoms. "
        "`interface_contacts_lost` counts cross-chain contacts the substitution removes. "
        "`delta_aggregation` is the AGGRESCAN window change at that site. "
        "Guessed gained contacts are omitted. No mutant structure is built. "
        "AlphaMissense is not included, because an S669 row is a PDB chain and an experimental folding ΔΔG, not a clinical variant.",
        "",
        "On these crystal and NMR entries the `plddt_confidence` column is the PDB B-factor, not an AlphaFold confidence.",
        "",
        f"Scored {len(scored)} of {len(rows)}.",
        "",
        "Experimental ΔΔG uses the S669 sign: positive is destabilizing.",
        "",
        "| Feature | Pearson r | Spearman ρ |",
        "| --- | ---: | ---: |",
    ]
    for item in correlations:
        lines.append(
            f"| {item['feature']} | {_format_r(float(item['pearson']))} | {_format_r(float(item['spearman']))} |"
        )
    lines.extend(
        [
            "",
            "`heuristic_score` is the existing untrained S669 sum of these same features. "
            "The other rows are the individual features, unfitted.",
            "",
        ]
    )
    return "\n".join(lines)


def run(variants_path: Path, out_dir: Path, pdb_dir: Path, *, limit: int | None, workers: int) -> dict[str, Any]:
    variants = load_variants(variants_path)
    if limit is not None:
        variants = variants[:limit]
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in variants:
        groups.setdefault(row["pdb"], []).append(row)

    tasks = []
    failed: list[dict[str, Any]] = []
    for pdb_id, rows in groups.items():
        source = pdb_dir / f"{pdb_id}.pdb"
        model_path = pdb_dir / f"{pdb_id}.model0.pdb"
        try:
            write_first_model(source, model_path)
        except Exception as exc:
            for row in rows:
                failed.append(_blank(row, "structure_failed", str(exc)))
            print(f"[WARN] {pdb_id}: {exc}")
            continue
        tasks.append({"pdb_path": str(model_path), "rows": rows})

    scored: list[dict[str, Any]] = list(failed)
    worker_count = max(1, min(workers, len(tasks) or 1))
    if tasks and worker_count == 1:
        for index, task in enumerate(tasks, start=1):
            scored.extend(score_pdb_group(task))
            print(f"[INFO] {index}/{len(tasks)} {Path(task['pdb_path']).stem}", flush=True)
    elif tasks:
        with ProcessPoolExecutor(max_workers=worker_count) as pool:
            for index, group in enumerate(pool.map(score_pdb_group, tasks), start=1):
                scored.extend(group)
                print(f"[INFO] {index}/{len(tasks)} structures", flush=True)

    order = {
        (row["pdb"], row["chain"], row["position"], row["mut"]): index
        for index, row in enumerate(variants)
    }
    scored.sort(key=lambda row: order[(row["pdb"], row["chain"], int(row["position"]), row["mut"])])
    paired = [row for row in scored if row["status"] == "scored"]
    correlations = correlate(paired)

    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "s669_feature_vectors.csv"
    report_path = out_dir / "s669_feature_vector_report.md"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(scored)
    report_path.write_text(render_report(scored, correlations), encoding="utf-8")
    print(f"[OK] scored {len(paired)}/{len(variants)}")
    for item in correlations:
        print(f"  {item['feature']}: pearson {_format_r(float(item['pearson']))} spearman {_format_r(float(item['spearman']))}")
    print(f"[OK] {report_path}")
    return {"scored": len(paired), "variants": len(variants), "correlations": correlations, "report": str(report_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export structural feature vectors for the S669 direct set.")
    parser.add_argument("--variants", type=Path, default=DEFAULT_VARIANTS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--pdb-dir", type=Path, default=DEFAULT_PDB_DIR)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=max(1, min(4, os.cpu_count() or 1)))
    args = parser.parse_args(argv)
    run(args.variants, args.out_dir, args.pdb_dir, limit=args.limit, workers=args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
