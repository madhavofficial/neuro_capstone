import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple


@dataclass(frozen=True)
class Target:
    gene: str
    variant: Optional[str] = None


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _parse_batch_line(line: str) -> Optional[Target]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    # Allow comma-separated or whitespace-separated formats:
    #   SNCA A53T
    #   SNCA,A53T
    #   SNCA
    tokens = [t for t in stripped.replace(",", " ").split() if t]
    if not tokens:
        return None

    if len(tokens) == 1:
        return Target(gene=tokens[0], variant=None)

    return Target(gene=tokens[0], variant=tokens[1])


def load_targets(batch_file: Optional[str], gene: Optional[str], variant: Optional[str]) -> list[Target]:
    if batch_file:
        with open(batch_file, "r") as f:
            targets: list[Target] = []
            for line in f:
                target = _parse_batch_line(line)
                if target:
                    targets.append(target)
        return targets

    if not gene:
        raise ValueError("gene is required unless --batch is provided")

    return [Target(gene=gene, variant=variant)]


def save_physics_json(pdb_path: str, variant: str, physics_data: dict, out_dir: Optional[str]) -> str:
    base_name = os.path.basename(pdb_path).replace(".pdb", "")
    filename = f"{base_name}_{variant}_physics.json"

    if out_dir:
        _ensure_dir(out_dir)
        out_path = os.path.join(out_dir, filename)
    else:
        out_path = os.path.join(os.path.dirname(pdb_path), filename)

    with open(out_path, "w") as f:
        json.dump(physics_data, f, indent=4)

    return out_path


def run_pipeline(
    gene: str,
    variant: Optional[str],
    *,
    uniprot_id: Optional[str] = None,
    manual_sequence: Optional[str] = None,
    chain_id: Optional[str] = None,
    run_structure: bool = True,
    run_context: bool = True,
    run_analysis: bool = True,
    analysis_out_dir: Optional[str] = None,
) -> Tuple[Optional[str], Optional[dict], Optional[str]]:
    """Runs structure -> context -> physics analysis.

    Returns (pdb_path, context_dict, physics_json_path).
    """

    pdb_path: Optional[str] = None
    context_data: Optional[dict] = None
    physics_json_path: Optional[str] = None

    if run_structure:
        try:
            from fetch_structure import get_structure
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "Structure step import failed. This usually means you're running the pipeline with a Python "
                "interpreter that doesn't have the project dependencies installed. "
                "If you have a venv, try: `source .venv/bin/activate` (Linux/macOS) "
                "or `.\\.venv\\Scripts\\Activate.ps1` (Windows PowerShell) then rerun with `python pipeline.py ...` "
                "(or run `./.venv/bin/python pipeline.py ...`). "
                f"Original error: {e}"
            )

        pdb_path = get_structure(
            gene,
            uniprot_id_arg=uniprot_id,
            manual_sequence=manual_sequence,
            # Mutation is handled virtually during analysis; keep structure WT/canonical.
            variant_tag=None,
        )
        if not pdb_path:
            raise RuntimeError(f"Structure step failed for {gene}{' ' + variant if variant else ''}")

    if run_context:
        try:
            from fetch_context import fetch_all_context
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "Context step import failed. This usually means you're running the pipeline with a Python "
                "interpreter that doesn't have the project dependencies installed. "
                "If you have a venv, try: `source .venv/bin/activate` (Linux/macOS) "
                "or `.\\.venv\\Scripts\\Activate.ps1` (Windows PowerShell) then rerun with `python pipeline.py ...` "
                "(or run `./.venv/bin/python pipeline.py ...`). "
                f"Original error: {e}"
            )

        context_data = fetch_all_context(gene, variant)
        if context_data is None:
            raise RuntimeError(f"Context step failed for {gene}{' ' + variant if variant else ''}")

    if run_analysis:
        if not variant:
            raise ValueError("--variant is required to run physics analysis")
        if not pdb_path:
            raise RuntimeError("No PDB available for analysis step")

        try:
            from analyze_structure import calculate_physics_metrics
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "Analysis step import failed. If the error mentions `Bio`/Biopython, you're likely not using the venv. "
                "Try: `source .venv/bin/activate` (Linux/macOS) "
                "or `.\\.venv\\Scripts\\Activate.ps1` (Windows PowerShell) then rerun with `python pipeline.py ...` "
                "(or run `./.venv/bin/python pipeline.py ...`). "
                f"Original error: {e}"
            )

        physics_data = calculate_physics_metrics(pdb_path, variant, chain_id=chain_id)
        if not physics_data:
            raise RuntimeError(f"Analysis step failed for {gene} {variant}")

        physics_json_path = save_physics_json(pdb_path, variant, physics_data, analysis_out_dir)

    return pdb_path, context_data, physics_json_path


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="One-command pipeline: structure -> context -> physics analysis",
    )

    parser.add_argument("gene", nargs="?", help="Gene symbol (e.g., SNCA)")
    parser.add_argument("--variant", help="Variant code (e.g., A53T)", default=None)

    parser.add_argument(
        "--batch",
        help="Path to a batch file with one target per line: 'GENE VARIANT' or 'GENE,VARIANT' (variant optional)",
        default=None,
    )

    # Pass-through options to fetch_structure
    parser.add_argument("--id", dest="uniprot_id", help="Optional UniProt ID", default=None)
    parser.add_argument(
        "--seq",
        dest="manual_sequence",
        help="Manual WT/canonical sequence override for structure folding (used if AlphaFold is unavailable)",
        default=None,
    )

    # Analysis options
    parser.add_argument(
        "--chain",
        dest="chain_id",
        help="Chain ID to analyze (passed to analyze_structure; default: first chain)",
        default=None,
    )

    # Pipeline controls
    parser.add_argument("--no-structure", action="store_true", help="Skip structure step")
    parser.add_argument("--no-context", action="store_true", help="Skip context step")
    parser.add_argument("--no-analysis", action="store_true", help="Skip analysis step")
    parser.add_argument(
        "--analysis-out-dir",
        help="Where to save physics JSON output (default: data/analysis)",
        default="data/analysis",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    # --seq is allowed without --variant (WT folding override).

    try:
        targets = load_targets(args.batch, args.gene, args.variant)
    except Exception as e:
        print(f"❌ Error: {e}")
        return 2

    failures: list[str] = []

    for target in targets:
        label = f"{target.gene}{' ' + target.variant if target.variant else ''}".strip()
        print(f"\n==============================\n🚀 PIPELINE TARGET: {label}\n==============================")
        try:
            effective_run_analysis = (not args.no_analysis) and bool(target.variant)
            if (not args.no_analysis) and (not target.variant):
                print("ℹ️  No variant provided for this target; skipping physics analysis.")

            pdb_path, _context, physics_json_path = run_pipeline(
                target.gene,
                target.variant,
                uniprot_id=args.uniprot_id,
                manual_sequence=args.manual_sequence,
                chain_id=args.chain_id,
                run_structure=not args.no_structure,
                run_context=not args.no_context,
                run_analysis=effective_run_analysis,
                analysis_out_dir=args.analysis_out_dir,
            )

            if pdb_path:
                print(f"✅ Structure: {pdb_path}")
            if physics_json_path:
                print(f"✅ Physics JSON: {physics_json_path}")

            # Automatically invoke NLP query generation if both gene and variant are present
            if target.gene and target.variant:
                import subprocess
                nlp_args = [sys.executable, os.path.join(os.path.dirname(__file__), "nlp_formation.py"), target.gene, target.variant, "--data-dir", "data"]
                try:
                    print(f"📝 Generating NLP query for {target.gene} {target.variant}...")
                    result = subprocess.run(nlp_args, capture_output=True, text=True)
                    print(result.stdout)
                    if result.returncode != 0:
                        print(f"⚠️  NLP query generation failed: {result.stderr}")
                except Exception as e:
                    print(f"⚠️  Failed to run NLP query generation: {e}")
        except Exception as e:
            failures.append(f"{label}: {e}")
            print(f"❌ Pipeline failed for {label}: {e}")

    if failures:
        print("\nSome targets failed:")
        for item in failures:
            print(f"- {item}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
