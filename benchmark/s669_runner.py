"""Correlate wild-type structural heuristics with experimental S669 ΔΔG.

Each row is a virtual amino-acid substitution on one wild-type PDB. The runner
does not build a mutant structure. The collapsed score is an untrained sum of
the metrics ``analyze_protein`` already emits. Coefficients are feature scales,
not weights fit on S669.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Bio.PDB import PDBIO, Select  # noqa: E402

from analyze_structure import (  # noqa: E402
    analyze_protein,
    find_residue_by_resseq,
    get_chain,
    load_structure,
    normalize_resname,
    one_to_three,
)

DEFAULT_VARIANTS = ROOT / "data" / "benchmarks" / "s669_variants.csv"
DEFAULT_OUT_DIR = ROOT / "data" / "benchmarks"
DEFAULT_PDB_DIR = ROOT / "data" / "benchmarks" / "s669_structures"
RCSB_URL = "https://files.rcsb.org/download/{pdb_id}.pdb"

# Pancotti et al., Briefings in Bioinformatics 23:bbab555 (2022), S669 direct.
# Pearson r of the simple predictors on that set: FoldX 0.22, DDGun 0.41, DDGun3D 0.43.
PUBLISHED_SIMPLE_PEARSON_FLOOR = 0.22
PUBLISHED_SIMPLE_PREDICTORS = (
    ("FoldX", 0.22),
    ("DDGun", 0.41),
    ("DDGun3D", 0.43),
)
STRUCTURED_SECONDARY = {"Alpha Helix", "Beta Bridge", "Beta Sheet", "Helix-3", "Helix-5"}
VOLUME_SCALE = 60.0
HYDRO_SCALE = 4.5


def same_amino_acid(pdb_resname: str, expected_one: str) -> bool:
    """True when a PDB residue name is the wild-type amino acid, including protonation aliases."""
    observed = normalize_resname(pdb_resname)
    if observed in {"HSD", "HSE", "HIP"}:
        observed = "HIS"
    elif observed in {"CYX", "CYM"}:
        observed = "CYS"
    expected = one_to_three(expected_one)
    return bool(expected) and observed == expected


def _burial(exposure: str, sasa: float) -> float:
    if exposure == "Buried" or sasa < 10:
        return 1.0
    if exposure == "Partially Exposed" or sasa < 40:
        return 0.5
    return 0.2


def collapse_stability_score(analysis: dict[str, Any]) -> float:
    """Collapse one ``analyze_protein`` result into a monomer-stability score.

    Positive means the virtual substitution is predicted to destabilize folding.
    SASA sets the burial weight. DSSP sets the structure weight and the proline
    helix-breaker flag. Volume, hydropathy, and charge come from residue tables.
    Only contacts measured on the wild-type atoms are counted: lost hydrogen
    bonds, lost salt bridges, and lost disulfides. Guessed gained contacts are
    left out, because the mutant side chain is never placed.
    """
    deltas = analysis["deltas"]
    context = analysis["structural_context_wt"]
    audit = analysis["stability_audit"]
    wild = analysis["wild_type"]
    mutant = analysis["mutant_properties"]

    burial = _burial(str(context.get("exposure") or ""), float(context["sasa"]))
    structure_weight = 1.0 if context.get("secondary_structure") in STRUCTURED_SECONDARY else 0.5
    volume_term = burial * abs(float(deltas["delta_volume"])) / VOLUME_SCALE
    hydro_term = burial * (-float(deltas["delta_hydrophobicity"])) / HYDRO_SCALE
    charge_term = burial * (abs(float(mutant["charge"])) - abs(float(wild["charge"])))
    contact_term = (
        int(audit["h_bonds_lost_est"])
        + len(audit["salt_bridges_lost"])
        + len(audit["disulfides_lost"])
    )
    strain = str(audit.get("backbone_strain") or "None")
    strain_term = 0.0 if strain == "None" else 1.0
    return structure_weight * (volume_term + hydro_term + charge_term) + contact_term + strain_term


def pearson(x: list[float], y: list[float]) -> float:
    left = np.asarray(x, dtype=float)
    right = np.asarray(y, dtype=float)
    if left.size < 3 or np.std(left) == 0 or np.std(right) == 0:
        return float("nan")
    return float(np.corrcoef(left, right)[0, 1])


def _average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    sorted_values = values[order]
    start = 0
    while start < len(values):
        stop = start
        while stop + 1 < len(values) and sorted_values[stop + 1] == sorted_values[start]:
            stop += 1
        average = (start + 1 + stop + 1) / 2.0
        for index in range(start, stop + 1):
            ranks[order[index]] = average
        start = stop + 1
    return ranks


def spearman(x: list[float], y: list[float]) -> float:
    left = np.asarray(x, dtype=float)
    right = np.asarray(y, dtype=float)
    if left.size < 3:
        return float("nan")
    return pearson(_average_ranks(left).tolist(), _average_ranks(right).tolist())


def correlation_meets_simple_predictors(pearson_r: float) -> bool:
    """True when Pearson is at least FoldX on the S669 direct set."""
    return pearson_r == pearson_r and pearson_r >= PUBLISHED_SIMPLE_PEARSON_FLOOR


def load_variants(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    required = {"pdb", "chain", "wt", "position", "mut", "ddg"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f"S669 table is missing columns: {sorted(required - set(rows[0] if rows else []))}")
    parsed: list[dict[str, Any]] = []
    for row in rows:
        parsed.append(
            {
                "pdb": row["pdb"].strip().upper(),
                "chain": row["chain"].strip(),
                "wt": row["wt"].strip().upper(),
                "position": int(row["position"]),
                "mut": row["mut"].strip().upper(),
                "ddg": float(row["ddg"]),
            }
        )
    return parsed


class _FirstModel(Select):
    def accept_model(self, model) -> bool:
        return model.id == 0


def write_first_model(source: Path, destination: Path) -> None:
    """Keep the first model. NMR bundles store every conformer in one file.

    ``analyze_protein`` reads residue geometry from model 0. Running solvent
    area on every conformer at once treats those conformers as one packed
    molecule, so the file passed to the scorer contains model 0 only.
    """
    if destination.exists() and destination.stat().st_size > 0 and destination.stat().st_mtime >= source.stat().st_mtime:
        return
    structure = load_structure(str(source))
    destination.parent.mkdir(parents=True, exist_ok=True)
    writer = PDBIO()
    writer.set_structure(structure)
    writer.save(str(destination), _FirstModel())


def download_pdb(pdb_id: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return
    response = requests.get(
        RCSB_URL.format(pdb_id=pdb_id),
        headers={"User-Agent": "neuro-capstone-s669/1.0"},
        timeout=60,
    )
    response.raise_for_status()
    destination.write_bytes(response.content)


def _residue_status(pdb_path: str, row: dict[str, Any]) -> str:
    structure = load_structure(pdb_path)
    try:
        chain = get_chain(structure[0], row["chain"])
    except KeyError:
        return "chain_missing"
    residue = find_residue_by_resseq(chain, int(row["position"]))
    if residue is None:
        return "residue_missing"
    if not same_amino_acid(residue.get_resname(), row["wt"]):
        return "residue_mismatch"
    return "ok"


def score_pdb_group(task: dict[str, Any]) -> list[dict[str, Any]]:
    """Score every variant that shares one downloaded wild-type PDB."""
    pdb_path = task["pdb_path"]
    scored: list[dict[str, Any]] = []
    for row in task["rows"]:
        record = dict(row)
        record["score"] = ""
        record["status"] = "analysis_failed"
        variant = f"{row['wt']}{row['position']}{row['mut']}"
        record["variant"] = variant
        try:
            status = _residue_status(pdb_path, row)
            if status != "ok":
                record["status"] = status
                scored.append(record)
                continue
            analysis = analyze_protein(pdb_path, variant, chain_id=row["chain"], verbose=False)
            if not analysis:
                record["status"] = "analysis_failed"
                scored.append(record)
                continue
            record["score"] = f"{collapse_stability_score(analysis):.6f}"
            record["status"] = "scored"
        except Exception as exc:
            record["status"] = "analysis_failed"
            record["detail"] = str(exc)
        scored.append(record)
    return scored


def _write_scores(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = ["pdb", "chain", "variant", "wt", "position", "mut", "ddg", "score", "status"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _format_r(value: float) -> str:
    if value != value:
        return "undefined"
    return f"{value:.3f}"


def render_report(
    *,
    variants: list[dict[str, Any]],
    scored: list[dict[str, Any]],
    pearson_r: float,
    spearman_r: float,
) -> str:
    chains = {(row["pdb"], row["chain"]) for row in variants}
    status_counts: dict[str, int] = {}
    for row in scored:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    scored_n = status_counts.get("scored", 0)
    keeps_name = correlation_meets_simple_predictors(pearson_r)
    if keeps_name:
        decision = (
            f"Pearson {_format_r(pearson_r)} is at or above {PUBLISHED_SIMPLE_PEARSON_FLOOR:.2f}, "
            "the low end of published simple stability predictors on the S669 direct set. "
            "The physics-engine name stays in the structure modules."
        )
    else:
        decision = (
            f"Pearson {_format_r(pearson_r)} is below {PUBLISHED_SIMPLE_PEARSON_FLOOR:.2f}, "
            "the FoldX result on this same direct set and the low end of the published simple predictors. "
            "In the modules this task owns, the calculation is named a structural heuristic. "
            "S669 is a monomer-stability check, not an aggregation test."
        )
    predictor_line = ", ".join(f"{name} {value:.2f}" for name, value in PUBLISHED_SIMPLE_PREDICTORS)
    skip_line = ", ".join(
        f"{name} {count}" for name, count in sorted(status_counts.items()) if name != "scored"
    ) or "none"
    return "\n".join(
        [
            "# S669 structural-heuristic check",
            "",
            "Each variant is a virtual amino-acid substitution on one wild-type PDB. "
            "Volume, hydropathy, and charge come from residue tables. SASA, DSSP, hydrogen bonds, "
            "salt bridges, and disulfides are read from that same wild-type model. "
            "NMR entries contribute their first model only. "
            "No mutant coordinate file is built.",
            "",
            "## Set",
            "",
            "The rows are the S669 direct set from Pancotti et al., Briefings in Bioinformatics 23:bbab555 (2022): "
            f"{len(variants)} variants across {len(chains)} PDB chains. "
            "The figure of about 1,338 variants is this set plus the reverse mutation of each row. "
            "The reverse coordinates in that paper are Robetta models of the mutant. "
            "This run scores the direct rows only, on the wild-type structure.",
            "",
            "Experimental ΔΔG uses the S669 sign: positive is destabilizing. "
            "The heuristic score uses the same direction.",
            "",
            "## Score",
            "",
            "The score is an untrained sum. Burial is 1.0 when SASA < 10 Å², 0.5 when SASA < 40 Å², and 0.2 otherwise. "
            "Helix and sheet sites keep the full packing terms; other DSSP labels halve them. "
            f"Volume contributes `burial * |ΔV| / {VOLUME_SCALE:.0f}`. "
            f"Hydropathy contributes `burial * (−ΔH) / {HYDRO_SCALE}`. "
            "Charge contributes `burial * (|q_mut| − |q_wt|)`. "
            "Lost hydrogen bonds, lost salt bridges, and lost disulfides each contribute 1 per contact measured on the wild-type atoms. "
            "Guessed gained contacts are omitted. "
            "A backbone-strain flag contributes 1. "
            "These scales were not fit on S669.",
            "",
            "## Result",
            "",
            f"Scored {scored_n} of {len(variants)}. Skipped: {skip_line}.",
            "",
            f"Pearson r = {_format_r(pearson_r)}",
            f"Spearman ρ = {_format_r(spearman_r)}",
            "",
            f"Published simple predictors on the S669 direct set, Pearson r: {predictor_line}.",
            "",
            "## Decision",
            "",
            decision,
            "",
            "## What a weak correlation leaves in place",
            "",
            "The site metrics stay. They still describe the wild-type substitution, and the literature query still uses them for aggregation and misfolding. "
            "TTR disease is tetramer dissociation. S669 measures monomer folding stability. "
            "This check does not replace the heuristics with ThermoMPNN.",
            "",
        ]
    )


def run(variants_path: Path, out_dir: Path, pdb_dir: Path, *, limit: int | None, workers: int) -> dict[str, Any]:
    variants = load_variants(variants_path)
    if limit is not None:
        variants = variants[:limit]
    pdb_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in variants:
        groups.setdefault(row["pdb"], []).append(row)

    tasks: list[dict[str, Any]] = []
    failed_rows: list[dict[str, Any]] = []
    for pdb_id, rows in groups.items():
        destination = pdb_dir / f"{pdb_id}.pdb"
        try:
            download_pdb(pdb_id, destination)
        except Exception as exc:
            for row in rows:
                failed = dict(row)
                failed["variant"] = f"{row['wt']}{row['position']}{row['mut']}"
                failed["score"] = ""
                failed["status"] = "download_failed"
                failed["detail"] = str(exc)
                failed_rows.append(failed)
            print(f"[WARN] {pdb_id}: {exc}")
            continue
        model_path = destination.with_name(f"{pdb_id}.model0.pdb")
        try:
            write_first_model(destination, model_path)
        except Exception as exc:
            for row in rows:
                failed = dict(row)
                failed["variant"] = f"{row['wt']}{row['position']}{row['mut']}"
                failed["score"] = ""
                failed["status"] = "download_failed"
                failed["detail"] = str(exc)
                failed_rows.append(failed)
            print(f"[WARN] {pdb_id} model: {exc}")
            continue
        tasks.append({"pdb_path": str(model_path), "rows": rows})

    scored_groups: list[dict[str, Any]] = list(failed_rows)
    worker_count = max(1, min(workers, len(tasks) or 1))
    if tasks and worker_count == 1:
        for index, task in enumerate(tasks, start=1):
            scored_groups.extend(score_pdb_group(task))
            print(f"[INFO] {index}/{len(tasks)} {Path(task['pdb_path']).stem}")
    elif tasks:
        with ProcessPoolExecutor(max_workers=worker_count) as pool:
            for index, group in enumerate(pool.map(score_pdb_group, tasks), start=1):
                scored_groups.extend(group)
                print(f"[INFO] {index}/{len(tasks)} structures")

    order = {
        (row["pdb"], row["chain"], row["position"], row["mut"]): index
        for index, row in enumerate(variants)
    }
    scored_groups.sort(key=lambda row: order[(row["pdb"], row["chain"], row["position"], row["mut"])])

    paired = [row for row in scored_groups if row["status"] == "scored"]
    pearson_r = pearson([float(row["score"]) for row in paired], [float(row["ddg"]) for row in paired])
    spearman_r = spearman([float(row["score"]) for row in paired], [float(row["ddg"]) for row in paired])

    scores_path = out_dir / "s669_scores.csv"
    report_path = out_dir / "s669_report.md"
    _write_scores(scores_path, scored_groups)
    report_path.write_text(
        render_report(variants=variants, scored=scored_groups, pearson_r=pearson_r, spearman_r=spearman_r),
        encoding="utf-8",
    )
    print(f"[OK] Pearson {pearson_r:.3f}  Spearman {spearman_r:.3f}  scored {len(paired)}/{len(variants)}")
    print(f"[OK] {report_path}")
    return {
        "pearson": pearson_r,
        "spearman": spearman_r,
        "scored": len(paired),
        "variants": len(variants),
        "keep_physics_engine_name": correlation_meets_simple_predictors(pearson_r),
        "report": str(report_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Correlate structural heuristics with S669 experimental ΔΔG.")
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
