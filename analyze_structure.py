import Bio.PDB
from Bio.PDB import PDBParser, ShrakeRupley, PPBuilder, NeighborSearch
from Bio.PDB.DSSP import DSSP
import argparse
import os
import json
import sys
import numpy as np
import warnings

# Suppress Biopython warnings
warnings.filterwarnings('ignore')

# ==========================================
# 🧪 BIOPHYSICAL LOOKUP TABLES (THE CONSTANTS)
# ==========================================

AA_MAP_1_TO_3 = {
    'A': 'ALA', 'R': 'ARG', 'N': 'ASN', 'D': 'ASP', 'C': 'CYS',
    'Q': 'GLN', 'E': 'GLU', 'G': 'GLY', 'H': 'HIS', 'I': 'ILE',
    'L': 'LEU', 'K': 'LYS', 'M': 'MET', 'F': 'PHE', 'P': 'PRO',
    'S': 'SER', 'T': 'THR', 'W': 'TRP', 'Y': 'TYR', 'V': 'VAL'
}

# Charged side-chain atom names for salt bridge detection.
CHARGED_ATOMS = {
    "ARG": ["NH1", "NH2"],
    "LYS": ["NZ"],
    "HIS": ["ND1", "NE2"],
    "ASP": ["OD1", "OD2"],
    "GLU": ["OE1", "OE2"],
}

# Used for a stricter GLY -> rigid substitution backbone warning.
RIGID_RESIDUES = {"VAL", "ILE", "THR", "TRP", "PHE", "TYR", "LEU"}

POLAR_ATOM_NAMES = {
    "O",
    "N",
    "OD1",
    "OD2",
    "OE1",
    "OE2",
    "ND1",
    "NE2",
    "NZ",
    "OH",
    "OG",
    "OG1",
}

# 1. Hydrophobicity (Kyte-Doolittle)
HYDROPHOBICITY = {
    'ILE': 4.5, 'VAL': 4.2, 'LEU': 3.8, 'PHE': 2.8, 'CYS': 2.5,
    'MET': 1.9, 'ALA': 1.8, 'GLY': -0.4, 'THR': -0.7, 'SER': -0.8,
    'TRP': -0.9, 'TYR': -1.3, 'PRO': -1.6, 'HIS': -3.2, 'GLU': -3.5,
    'GLN': -3.5, 'ASP': -3.5, 'ASN': -3.5, 'LYS': -3.9, 'ARG': -4.5
}

# 2. Charge (pH 7.4)
CHARGE = {
    'ARG': 1, 'LYS': 1, 'HIS': 0.1, 
    'ASP': -1, 'GLU': -1,
    'ALA': 0, 'VAL': 0, 'LEU': 0, 'ILE': 0, 'MET': 0, 'PHE': 0, 'TRP': 0, 
    'PRO': 0, 'GLY': 0, 'SER': 0, 'THR': 0, 'CYS': 0, 'TYR': 0, 'ASN': 0, 'GLN': 0
}

# 3. Van der Waals Volume
VOLUME = {
    'GLY': 60.1, 'ALA': 88.6, 'SER': 89.0, 'CYS': 108.5, 'PRO': 112.7,
    'ASP': 111.1, 'THR': 116.1, 'ASN': 114.1, 'VAL': 140.0, 'GLU': 138.4,
    'GLN': 143.8, 'HIS': 153.2, 'MET': 162.9, 'ILE': 166.7, 'LEU': 166.7,
    'LYS': 168.6, 'ARG': 173.4, 'PHE': 189.9, 'TYR': 193.6, 'TRP': 227.8
}

def one_to_three(one_letter):
    return AA_MAP_1_TO_3.get(one_letter.upper())


def parse_variant_code(variant_code: str) -> tuple[str, int, str, str, str]:
    """Parses e.g. 'A53T' -> (wt_1, pos, mut_1, wt_3, mut_3)."""
    import re

    match = re.match(r"([A-Z])(\d+)([A-Z])", variant_code.upper())
    if not match:
        raise ValueError("Invalid variant format. Use format like 'A53T'.")

    wt_1, pos_str, mut_1 = match.groups()
    pos = int(pos_str)

    wt_3 = one_to_three(wt_1)
    mut_3 = one_to_three(mut_1)
    if not wt_3 or not mut_3:
        raise ValueError(f"Invalid amino acid code in variant '{variant_code}'.")

    return wt_1, pos, mut_1, wt_3, mut_3


def load_structure(pdb_path: str):
    parser = PDBParser(QUIET=True)
    return parser.get_structure("protein", pdb_path)


def get_chain(model, chain_id: str | None):
    if chain_id is None:
        return next(model.get_chains())
    return model[chain_id]


def find_residue_by_resseq(chain, resseq: int):
    """Finds a standard amino-acid residue by its sequence number (resseq)."""
    for residue in chain:
        if residue.id[0] != " ":
            continue
        if residue.id[1] == resseq:
            return residue
    return None


def _min_atom_distance(res1, atom_names1: list[str], res2, atom_names2: list[str]) -> float:
    """Returns min distance between named atoms in two residues; inf if none exist."""
    min_dist = float("inf")
    found = False
    for atom_name_1 in atom_names1:
        if atom_name_1 not in res1:
            continue
        for atom_name_2 in atom_names2:
            if atom_name_2 not in res2:
                continue
            dist = res1[atom_name_1] - res2[atom_name_2]
            if dist < min_dist:
                min_dist = dist
            found = True
    return min_dist if found else float("inf")


def _iter_polar_atoms(residue):
    for atom in residue:
        atom_name = atom.get_name().strip()
        if atom_name in POLAR_ATOM_NAMES:
            yield atom


def safe_secondary_structure(model, pdb_path: str, chain_id: str, residue) -> str:
    """Returns DSSP secondary structure label if mkdssp/dssp is installed."""
    sec_struct = "Unknown"
    try:
        dssp = DSSP(model, pdb_path, dssp="mkdssp")
        dssp_key = (chain_id, residue.id)
        if dssp_key in dssp:
            code = dssp[dssp_key][2]
            sec_struct_map = {
                "H": "Alpha Helix",
                "B": "Beta Bridge",
                "E": "Beta Sheet",
                "G": "Helix-3",
                "I": "Helix-5",
                "T": "Turn",
                "S": "Bend",
                "-": "Loop",
            }
            sec_struct = sec_struct_map.get(code, "Loop")
    except Exception as e:
        print(f"⚠️ DSSP Warning: {e}. (Is mkdssp installed?)")
    return sec_struct


def compute_site_metrics(structure, pdb_path: str, *, model_id: int = 0, chain_id: str | None, resseq: int) -> dict:
    model = structure[model_id]
    chain = get_chain(model, chain_id)
    chain_id_resolved = chain.id

    residue = find_residue_by_resseq(chain, resseq)
    if residue is None:
        raise ValueError(f"Residue {resseq} not found in chain {chain_id_resolved}.")

    # SASA needs pre-computation on the structure
    sr = ShrakeRupley()
    sr.compute(structure, level="R")
    sasa = getattr(residue, "sasa", 0.0)

    # AlphaFold-like PDBs store confidence in B-factor
    b_factors = [atom.bfactor for atom in residue]
    plddt = float(np.mean(b_factors)) if b_factors else 0.0

    sec_struct = safe_secondary_structure(model, pdb_path, chain_id_resolved, residue)

    # Local packing proxy: number of neighbor residues within 5Å of CA (or last atom)
    atoms = Bio.PDB.Selection.unfold_entities(model, "A")
    ns = NeighborSearch(atoms)
    center = residue["CA"] if "CA" in residue else list(residue)[-1]
    neighbors = ns.search(center.get_coord(), 5.0, level="R")
    neighbor_count = len([r for r in neighbors if r is not residue])

    return {
        "chain": chain_id_resolved,
        "resseq": resseq,
        "resname": residue.get_resname(),
        "sasa": round(float(sasa), 2),
        "exposure": "Buried" if sasa < 15 else "Exposed",
        "plddt_confidence": round(plddt, 2),
        "secondary_structure": sec_struct,
        "neighbor_residue_count_5A": int(neighbor_count),
    }

# ==========================================
# ⚙️ INTERACTION ENGINE (Features 7, 8, 9)
# ==========================================
def get_interactions(structure, model_id, chain_id, res_id, wt_resname, mut_resname):
    """
    Scans the Wild Type structure for bonds that WILL BE BROKEN by the mutation.
    """
    model = structure[model_id]
    try:
        chain = model[chain_id]
    except KeyError:
        return {
            "salt_bridges_lost": [],
            "disulfides_lost": [],
            "h_bonds_lost_est": 0,
        }

    target_res = find_residue_by_resseq(chain, res_id)
    if target_res is None:
        return {
            "salt_bridges_lost": [],
            "disulfides_lost": [],
            "h_bonds_lost_est": 0,
        }

    interactions = {
        "salt_bridges_lost": [],
        "disulfides_lost": [],
        "h_bonds_lost_est": 0,
    }

    atoms = Bio.PDB.Selection.unfold_entities(model, "A")
    ns = NeighborSearch(atoms)

    # Broad neighbor search (sidechains can extend beyond CA distance).
    center_atom = target_res["CA"] if "CA" in target_res else list(target_res)[-1]
    neighbor_residues = ns.search(center_atom.get_coord(), 6.0, level="R")

    # 7) Salt bridges: charged atom distance < 4.0Å
    positive = {"ARG", "LYS", "HIS"}
    negative = {"ASP", "GLU"}
    if wt_resname in positive or wt_resname in negative:
        my_atoms = CHARGED_ATOMS.get(wt_resname, [])
        for neighbor in neighbor_residues:
            if neighbor is target_res:
                continue
            neighbor_name = neighbor.get_resname()
            if neighbor_name not in (positive | negative):
                continue

            # Ensure the WT residue is actually forming a salt bridge pre-mutation.
            is_opposite = (wt_resname in positive and neighbor_name in negative) or (
                wt_resname in negative and neighbor_name in positive
            )
            if not is_opposite:
                continue

            neighbor_atoms = CHARGED_ATOMS.get(neighbor_name, [])
            dist = _min_atom_distance(target_res, my_atoms, neighbor, neighbor_atoms)
            if dist >= 4.0:
                continue

            mut_is_neutral = mut_resname not in (positive | negative)
            mut_flips = (wt_resname in positive and mut_resname in negative) or (
                wt_resname in negative and mut_resname in positive
            )
            if mut_is_neutral or mut_flips:
                interactions["salt_bridges_lost"].append(f"{neighbor_name}{neighbor.id[1]}")

    # 8) Disulfides: SG-SG < 2.5Å
    if wt_resname == "CYS" and mut_resname != "CYS" and "SG" in target_res:
        candidate_residues = ns.search(target_res["SG"].get_coord(), 3.5, level="R")
        for neighbor in candidate_residues:
            if neighbor is target_res:
                continue
            if neighbor.get_resname() != "CYS" or "SG" not in neighbor:
                continue
            dist = target_res["SG"] - neighbor["SG"]
            if dist < 2.5:
                interactions["disulfides_lost"].append(f"{neighbor.get_resname()}{neighbor.id[1]}")

    # 9) H-bond loss proxy: count neighbors with any polar atom contact < 3.5Å
    polar_residues = {
        "SER",
        "THR",
        "TYR",
        "ASN",
        "GLN",
        "HIS",
        "TRP",
        "LYS",
        "ARG",
        "ASP",
        "GLU",
    }
    if wt_resname in polar_residues and mut_resname not in polar_residues:
        h_loss_count = 0
        target_polar_atoms = list(_iter_polar_atoms(target_res))
        if target_polar_atoms:
            for neighbor in neighbor_residues:
                if neighbor is target_res:
                    continue
                neighbor_polar_atoms = list(_iter_polar_atoms(neighbor))
                if not neighbor_polar_atoms:
                    continue
                min_dist = float("inf")
                for atom_1 in target_polar_atoms:
                    for atom_2 in neighbor_polar_atoms:
                        d = atom_1 - atom_2
                        if d < min_dist:
                            min_dist = d
                if min_dist < 3.5:
                    h_loss_count += 1
        interactions["h_bonds_lost_est"] = h_loss_count

    return interactions

# ==========================================
# 🧠 MAIN ANALYSIS LOGIC (Features 1-10)
# ==========================================
def analyze_protein(pdb_path, variant_code, *, chain_id: str | None = None):
    chain_label = chain_id if chain_id is not None else "<first>"
    print(f"--- 🧬 ANALYZING {variant_code} (chain {chain_label}) ---")
    
    # A. Parse Variant
    try:
        _wt_1, res_id, _mut_1, wt_3, mut_3 = parse_variant_code(variant_code)
    except ValueError as e:
        print(f"❌ {e}")
        return None
    
    # B. Load Structure
    structure = load_structure(pdb_path)
    model = structure[0]
    chain = get_chain(model, chain_id)
    target_res = find_residue_by_resseq(chain, res_id)
    if target_res is None:
        print(f"❌ Error: Residue {res_id} not found in PDB.")
        return None

    # C. Run DSSP (Feature 2: Secondary Structure)
    # NOTE: Requires 'dssp' or 'mkdssp' installed on OS
    sec_struct = safe_secondary_structure(model, pdb_path, chain.id, target_res)

    # D. Calculate Features
    
    # 1. SASA (Solvent Exposure)
    sr = ShrakeRupley()
    sr.compute(structure, level="R")
    sasa = getattr(target_res, "sasa", 0.0)
    
    # 3. pLDDT (Rigidity)
    plddt = float(np.mean([atom.bfactor for atom in target_res]))
    
    # 4-6. Deltas (Volume, Hydro, Charge)
    d_vol = VOLUME.get(mut_3, 0) - VOLUME.get(wt_3, 0)
    d_hydro = HYDROPHOBICITY.get(mut_3, 0) - HYDROPHOBICITY.get(wt_3, 0)
    d_charge = CHARGE.get(mut_3, 0) - CHARGE.get(wt_3, 0)
    
    # 7-9. Interactions (The "Lost" Checks)
    interaction_data = get_interactions(structure, 0, chain.id, res_id, wt_3, mut_3)
    
    # 10. Backbone Strain (Gly/Pro)
    strain_warning = "None"
    if wt_3 == "GLY" and mut_3 in RIGID_RESIDUES:
        strain_warning = "Glycine Flexibility Lost"
    if mut_3 == "PRO" and sec_struct in {"Alpha Helix", "Helix-3", "Helix-5"}:
        strain_warning = "Proline Helix Breaker"

    # E. Compile Final JSON
    result = {
        "variant": variant_code,
        "wild_type": {
            "residue": wt_3,
            "volume": VOLUME.get(wt_3, 0),
            "hydrophobicity": HYDROPHOBICITY.get(wt_3, 0),
            "charge": CHARGE.get(wt_3, 0)
        },
        "mutant_properties": {
            "residue": mut_3,
            "volume": VOLUME.get(mut_3, 0),
            "hydrophobicity": HYDROPHOBICITY.get(mut_3, 0),
            "charge": CHARGE.get(mut_3, 0)
        },
        "deltas": {
            "delta_volume": round(d_vol, 2),
            "delta_hydrophobicity": round(d_hydro, 2),
            "delta_charge": d_charge
        },
        "structural_context_wt": {
            "sasa": round(sasa, 2),
            "exposure": "Buried" if sasa < 15 else "Exposed",
            "secondary_structure": sec_struct,
            "plddt_confidence": round(plddt, 2)
        },
        "stability_audit": {
            "salt_bridges_lost": interaction_data['salt_bridges_lost'],
            "disulfides_lost": interaction_data['disulfides_lost'],
            "h_bonds_lost_est": interaction_data['h_bonds_lost_est'],
            "backbone_strain": strain_warning
        }
    }
    
    return result


def analyze_variant_pair(wt_pdb_path: str, mut_pdb_path: str, variant_code: str, *, chain_wt: str | None = None, chain_mut: str | None = None) -> dict:
    """Computes both intrinsic deltas (WT AA -> MUT AA) and observed structure-to-structure deltas."""
    _wt_1, resseq, _mut_1, wt_3, mut_3 = parse_variant_code(variant_code)

    wt_structure = load_structure(wt_pdb_path)
    mut_structure = load_structure(mut_pdb_path)

    wt_metrics = compute_site_metrics(wt_structure, wt_pdb_path, chain_id=chain_wt, resseq=resseq)
    mut_metrics = compute_site_metrics(mut_structure, mut_pdb_path, chain_id=chain_mut, resseq=resseq)

    d_vol = VOLUME.get(mut_3, 0) - VOLUME.get(wt_3, 0)
    d_hydro = HYDROPHOBICITY.get(mut_3, 0) - HYDROPHOBICITY.get(wt_3, 0)
    d_charge = CHARGE.get(mut_3, 0) - CHARGE.get(wt_3, 0)

    observed_deltas = {
        "delta_sasa": round(mut_metrics["sasa"] - wt_metrics["sasa"], 2),
        "delta_plddt_confidence": round(mut_metrics["plddt_confidence"] - wt_metrics["plddt_confidence"], 2),
        "delta_neighbor_residue_count_5A": int(mut_metrics["neighbor_residue_count_5A"] - wt_metrics["neighbor_residue_count_5A"]),
        "secondary_structure_changed": bool(mut_metrics["secondary_structure"] != wt_metrics["secondary_structure"]),
    }

    return {
        "variant": variant_code,
        "position": resseq,
        "wild_type": {
            "residue": wt_3,
            "volume": VOLUME.get(wt_3, 0),
            "hydrophobicity": HYDROPHOBICITY.get(wt_3, 0),
            "charge": CHARGE.get(wt_3, 0),
            "pdb": wt_pdb_path,
            "site_metrics": wt_metrics,
        },
        "mutant": {
            "residue": mut_3,
            "volume": VOLUME.get(mut_3, 0),
            "hydrophobicity": HYDROPHOBICITY.get(mut_3, 0),
            "charge": CHARGE.get(mut_3, 0),
            "pdb": mut_pdb_path,
            "site_metrics": mut_metrics,
        },
        "intrinsic_deltas": {
            "delta_volume": round(d_vol, 2),
            "delta_hydrophobicity": round(d_hydro, 2),
            "delta_charge": d_charge,
        },
        "structure_to_structure_deltas": observed_deltas,
    }


# Backwards-compatible entrypoint for pipeline.py
def calculate_physics_metrics(pdb_path: str, variant_code: str, *, chain_id: str | None = None) -> dict | None:
    """Pipeline-compatible wrapper.

    Returns a JSON-serializable dict for a single PDB (no WT-vs-MUT deltas unless you use analyze_variant_pair).
    """
    return analyze_protein(pdb_path, variant_code, chain_id=chain_id)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze intrinsic residue deltas and (optionally) WT-vs-MUT structural deltas.")
    parser.add_argument("pdb", nargs="?", help="Path to PDB file (single-structure mode)")
    parser.add_argument("variant", nargs="?", help="Mutation code (e.g. V50M)")
    parser.add_argument("--wt-pdb", help="WT PDB path (compare mode)", default=None)
    parser.add_argument("--mut-pdb", help="Mutant PDB path (compare mode)", default=None)
    parser.add_argument("--chain-wt", help="WT chain ID (compare mode)", default=None)
    parser.add_argument("--chain-mut", help="Mutant chain ID (compare mode)", default=None)
    parser.add_argument("--chain", help="Chain ID (single-structure mode; default: first chain)", default=None)
    parser.add_argument("--out", help="Output JSON path (default: <variant>_analysis.json)", default=None)
    args = parser.parse_args()

    if args.wt_pdb or args.mut_pdb:
        if not args.wt_pdb or not args.mut_pdb or not args.variant:
            print("❌ Compare mode requires --wt-pdb, --mut-pdb, and <variant>.")
            sys.exit(2)
        data = analyze_variant_pair(args.wt_pdb, args.mut_pdb, args.variant, chain_wt=args.chain_wt, chain_mut=args.chain_mut)
        out_file = args.out or f"{args.variant}_compare.json"
    else:
        if not args.pdb or not args.variant:
            print("❌ Single-structure mode requires <pdb> <variant>.")
            sys.exit(2)
        data = analyze_protein(args.pdb, args.variant, chain_id=args.chain)
        out_file = args.out or f"{args.variant}_analysis.json"

    with open(out_file, "w") as f:
        json.dump(data, f, indent=4)
    print(f"✅ Analysis saved to {out_file}")