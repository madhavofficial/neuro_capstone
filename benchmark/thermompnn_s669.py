"""Score the S669 direct set with ThermoMPNN.

ThermoMPNN reads the wild-type PDB and the amino-acid change. It does not
build a mutant structure. The position it expects is an index into the parsed
chain, matched the same way as ``ddgBenchDataset`` in the upstream repo.
That loader compares predictions with the negation of the S669 ΔΔG column,
so this report gives both signs.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path
from typing import Any

import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmark.s669_runner import (  # noqa: E402
    DEFAULT_PDB_DIR,
    DEFAULT_VARIANTS,
    load_variants,
    pearson,
    spearman,
    write_first_model,
)

DEFAULT_REPO = ROOT / "third_party" / "ThermoMPNN"
DEFAULT_OUT_DIR = ROOT / "data" / "benchmarks"


def resolve_sequence_index(seq: str, resn_list: list[str], position: int, wildtype: str) -> int | None:
    """Map a PDB residue number onto ThermoMPNN's sequence index.

    This follows ``ddgBenchDataset`` for the S669 directory: look the residue
    number up in ``resn_list``, then if the letter disagrees, shift by the
    number of gap characters in the parsed sequence.
    """
    try:
        index = resn_list.index(str(position))
    except ValueError:
        return None
    if index < len(seq) and seq[index] == wildtype:
        return index
    gaps = seq.count("-")
    index = index + gaps if gaps else index + 1
    if index < len(seq) and seq[index] == wildtype:
        return index
    return None


def _enable_full_checkpoints() -> None:
    original = torch.load

    def load(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return original(*args, **kwargs)

    torch.load = load


def load_thermompnn(repo: Path):
    """Load the published ThermoMPNN weights on CPU."""
    _enable_full_checkpoints()
    repo = repo.resolve()
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    os.environ.setdefault("WANDB_MODE", "disabled")

    from omegaconf import OmegaConf
    from train_thermompnn import TransferModelPL

    config = OmegaConf.create(
        {
            "platform": {"thermompnn_dir": str(repo), "accel": "cpu", "cache_dir": str(repo / "cache")},
            "training": {
                "num_workers": 0,
                "learn_rate": 0.001,
                "epochs": 100,
                "lr_schedule": True,
            },
            "model": {
                "hidden_dims": [64, 32],
                "subtract_mut": True,
                "num_final_layers": 2,
                "freeze_weights": True,
                "load_pretrained": True,
                "lightattn": True,
                "lr_schedule": True,
            },
        }
    )
    checkpoint = repo / "models" / "thermoMPNN_default.pt"
    if not checkpoint.is_file():
        raise FileNotFoundError(f"ThermoMPNN weights not found at {checkpoint}")
    wrapper = TransferModelPL.load_from_checkpoint(str(checkpoint), cfg=config, map_location="cpu")
    model = wrapper.model.eval()
    return model


def score_structure(model, pdb_path: Path, chain: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from datasets import Mutation
    from protein_mpnn_utils import alt_parse_PDB

    parsed = alt_parse_PDB(str(pdb_path), [chain])
    if not parsed or not isinstance(parsed[0].get("seq"), str):
        failed = []
        for row in rows:
            record = dict(row)
            record["variant"] = f"{row['wt']}{row['position']}{row['mut']}"
            record["score"] = ""
            record["status"] = "parse_failed"
            failed.append(record)
        return failed

    pdb = parsed[0]
    mutations = []
    pending: list[dict[str, Any]] = []
    scored: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        record["variant"] = f"{row['wt']}{row['position']}{row['mut']}"
        index = resolve_sequence_index(pdb["seq"], list(pdb["resn_list"]), int(row["position"]), row["wt"])
        if index is None:
            record["score"] = ""
            record["status"] = "residue_mismatch"
            scored.append(record)
            continue
        mutations.append(
            Mutation(
                position=index,
                wildtype=pdb["seq"][index],
                mutation=row["mut"],
                ddG=None,
                pdb=pdb.get("name", ""),
            )
        )
        pending.append(record)

    if mutations:
        with torch.no_grad():
            predictions, _ = model([pdb], mutations)
        for record, mutation, prediction in zip(pending, mutations, predictions):
            if prediction is None:
                record["score"] = ""
                record["status"] = "analysis_failed"
            else:
                record["score"] = f"{float(prediction['ddG'].detach().cpu().item()):.6f}"
                record["status"] = "scored"
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


def render_report(variants: list[dict[str, Any]], scored: list[dict[str, Any]], raw_r: float, flipped_r: float, raw_s: float, flipped_s: float) -> str:
    counts: dict[str, int] = {}
    for row in scored:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    skip_line = ", ".join(f"{name} {count}" for name, count in sorted(counts.items()) if name != "scored") or "none"
    return "\n".join(
        [
            "# ThermoMPNN on S669",
            "",
            "ThermoMPNN reads the wild-type PDB and the amino-acid change. No mutant coordinate file is built. "
            "NMR entries use the first model only. Weights are `thermoMPNN_default.pt` from Kuhlman-Lab/ThermoMPNN.",
            "",
            f"Scored {counts.get('scored', 0)} of {len(variants)}. Skipped: {skip_line}.",
            "",
            "The S669 table in this repo uses positive ΔΔG for a destabilizing mutation. "
            "ThermoMPNN's own S669 loader multiplies that column by −1 before scoring, so both correlations are reported.",
            "",
            f"Pearson vs experimental ΔΔG = {_format_r(raw_r)}",
            f"Spearman vs experimental ΔΔG = {_format_r(raw_s)}",
            "",
            f"Pearson vs −ΔΔG (ThermoMPNN S669 convention) = {_format_r(flipped_r)}",
            f"Spearman vs −ΔΔG (ThermoMPNN S669 convention) = {_format_r(flipped_s)}",
            "",
            "Published ThermoMPNN Pearson on S669 is 0.43 (Dieckhaus et al., PNAS 2024). "
            "FoldX is 0.22 and Rosetta is 0.39 on the direct set (Pancotti et al., 2022).",
            "",
        ]
    )


def run(variants_path: Path, pdb_dir: Path, out_dir: Path, repo: Path, *, limit: int | None) -> dict[str, float]:
    variants = load_variants(variants_path)
    if limit is not None:
        variants = variants[:limit]
    model = load_thermompnn(repo)

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in variants:
        groups.setdefault((row["pdb"], row["chain"]), []).append(row)

    scored: list[dict[str, Any]] = []
    for index, ((pdb_id, chain), rows) in enumerate(groups.items(), start=1):
        source = pdb_dir / f"{pdb_id}.pdb"
        model_path = pdb_dir / f"{pdb_id}.model0.pdb"
        if not source.is_file():
            for row in rows:
                record = dict(row)
                record["variant"] = f"{row['wt']}{row['position']}{row['mut']}"
                record["score"] = ""
                record["status"] = "download_failed"
                scored.append(record)
            print(f"[WARN] missing {source}")
            continue
        write_first_model(source, model_path)
        scored.extend(score_structure(model, model_path, chain, rows))
        print(f"[INFO] {index}/{len(groups)} {pdb_id} chain {chain}")

    order = {(row["pdb"], row["chain"], row["position"], row["mut"]): i for i, row in enumerate(variants)}
    scored.sort(key=lambda row: order[(row["pdb"], row["chain"], row["position"], row["mut"])])
    paired = [row for row in scored if row["status"] == "scored"]
    predicted = [float(row["score"]) for row in paired]
    observed = [float(row["ddg"]) for row in paired]
    flipped = [-value for value in observed]
    raw_r, raw_s = pearson(predicted, observed), spearman(predicted, observed)
    flipped_r, flipped_s = pearson(predicted, flipped), spearman(predicted, flipped)

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_scores(out_dir / "thermompnn_s669_scores.csv", scored)
    report = out_dir / "thermompnn_s669_report.md"
    report.write_text(
        render_report(variants, scored, raw_r, flipped_r, raw_s, flipped_s),
        encoding="utf-8",
    )
    print(f"[OK] Pearson {raw_r:.3f} (flipped {flipped_r:.3f})  scored {len(paired)}/{len(variants)}")
    print(f"[OK] {report}")
    return {"pearson": raw_r, "pearson_flipped": flipped_r, "spearman": raw_s, "spearman_flipped": flipped_s}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score S669 with ThermoMPNN.")
    parser.add_argument("--variants", type=Path, default=DEFAULT_VARIANTS)
    parser.add_argument("--pdb-dir", type=Path, default=DEFAULT_PDB_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    run(args.variants, args.pdb_dir, args.out_dir, args.repo, limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
