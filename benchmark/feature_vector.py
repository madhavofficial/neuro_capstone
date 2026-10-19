"""Export the blinded structural feature vector for one variant.

The vector is the wild-type site measurement plus the amino-acid table change.
Every variant also gets ``interface_contacts_lost`` and ``delta_aggregation``.
A one-chain structure has no interface count. Guessed gained contacts are
omitted because the mutant side chain is never placed. ClinVar is not a feature.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STRUCTURAL_FEATURE_KEYS = (
    "exposure",
    "sasa",
    "secondary_structure",
    "plddt_confidence",
    "delta_volume",
    "delta_hydrophobicity",
    "delta_charge",
    "backbone_strain",
    "salt_bridges_lost",
    "disulfides_lost",
    "h_bonds_lost_est",
    "interface_contacts_lost",
    "delta_aggregation",
    "monomer_ddg",
)

# Contacts inferred from a side chain that was never built.
GUESSED_GAIN_KEYS = (
    "salt_bridges_gained",
    "disulfides_gained",
    "h_bonds_gained_est",
)


def alphamissense_score(context: dict[str, Any] | None) -> float | None:
    """Return the AlphaMissense score from a ``fetch_context`` payload.

    Clinical blocks on that payload, including ClinVar, are ignored.
    """
    if not isinstance(context, dict):
        return None
    block = context.get("alphamissense_sniper")
    if not isinstance(block, dict) or block.get("score") is None:
        return None
    return float(block["score"])


def structural_features(analysis: dict[str, Any]) -> dict[str, Any]:
    """Keep the measured wild-type site and the residue-table deltas."""
    site = analysis["structural_context_wt"]
    deltas = analysis["deltas"]
    audit = analysis["stability_audit"]
    features = {
        "exposure": site.get("exposure"),
        "sasa": site.get("sasa"),
        "secondary_structure": site.get("secondary_structure"),
        "plddt_confidence": site.get("plddt_confidence"),
        "delta_volume": deltas.get("delta_volume"),
        "delta_hydrophobicity": deltas.get("delta_hydrophobicity"),
        "delta_charge": deltas.get("delta_charge"),
        "backbone_strain": audit.get("backbone_strain"),
        "salt_bridges_lost": list(audit.get("salt_bridges_lost") or []),
        "disulfides_lost": list(audit.get("disulfides_lost") or []),
        "h_bonds_lost_est": int(audit.get("h_bonds_lost_est") or 0),
        "interface_contacts_lost": int(analysis.get("interface_contacts_lost") or 0),
        "delta_aggregation": analysis.get("delta_aggregation", 0.0),
        "monomer_ddg": analysis.get("monomer_ddg"),
    }
    missing = [key for key in STRUCTURAL_FEATURE_KEYS if key not in features]
    if missing:
        raise KeyError(f"structural feature vector is missing {missing}")
    return features


def build_feature_row(
    gene: str,
    variant: str,
    analysis: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One gold-set row: AlphaMissense score plus the structural features."""
    return {
        "gene": gene,
        "variant": variant,
        "alphamissense_score": alphamissense_score(context),
        "structural_features": structural_features(analysis),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Print one blinded feature row as JSON.")
    parser.add_argument("--gene", required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--pdb", required=True, type=Path)
    parser.add_argument("--chain", default=None)
    parser.add_argument(
        "--context",
        type=Path,
        default=None,
        help="Optional fetch_context JSON. Only the AlphaMissense score is read.",
    )
    args = parser.parse_args()

    from analyze_structure import analyze_protein

    analysis = analyze_protein(
        str(args.pdb),
        args.variant,
        chain_id=args.chain,
        verbose=False,
    )
    if not analysis:
        raise SystemExit(f"No structural features for {args.gene} {args.variant}")

    context = None
    if args.context is not None:
        context = json.loads(args.context.read_text())
    row = build_feature_row(args.gene, args.variant, analysis, context)
    json.dump(row, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
