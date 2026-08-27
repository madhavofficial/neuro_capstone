from __future__ import annotations

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


def _as_float_or_none(x):
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _format_cell(val, *, digits: int = 2) -> str:
    if val is None:
        return "N/A"
    if isinstance(val, (int, np.integer)):
        return str(int(val))
    if isinstance(val, (float, np.floating)):
        return f"{float(val):.{digits}f}"
    return str(val)


def _format_delta(val, *, digits: int = 2) -> str:
    if val is None:
        return "N/A"
    try:
        f = float(val)
        sign = "+" if f > 0 else ""
        return f"{sign}{f:.{digits}f}"
    except Exception:
        return str(val)


def _print_comparison_table(comparison_view: dict, *, title: str | None = None):
    if title:
        print(title)

    rows = []
    for key, triple in comparison_view.items():
        if not isinstance(triple, dict) or not {"wt", "mut", "delta"}.issubset(triple.keys()):
            continue
        rows.append(
            (
                key,
                _format_cell(triple.get("wt")),
                _format_cell(triple.get("mut")),
                _format_delta(triple.get("delta")),
            )
        )

    if not rows:
        return

    headers = ("Property", "WT", "MUT", "Δ")
    col1 = max(len(headers[0]), max(len(r[0]) for r in rows))
    col2 = max(len(headers[1]), max(len(r[1]) for r in rows))
    col3 = max(len(headers[2]), max(len(r[2]) for r in rows))
    col4 = max(len(headers[3]), max(len(r[3]) for r in rows))

    def line(ch: str = "-"):
        return f"{ch * (col1 + col2 + col3 + col4 + 9)}"

    print(line("="))
    print(f"{headers[0]:<{col1}} | {headers[1]:>{col2}} | {headers[2]:>{col3}} | {headers[3]:>{col4}}")
    print(line("-"))
    for prop, wt, mut, delta in rows:
        print(f"{prop:<{col1}} | {wt:>{col2}} | {mut:>{col3}} | {delta:>{col4}}")
    print(line("="))


def _default_physics_json_path(pdb_path: str, variant_code: str, out_dir: str = "data/analysis") -> str:
    base_name = os.path.basename(pdb_path).replace(".pdb", "")
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, f"{base_name}_{variant_code}_physics.json")

# ==========================================
#  BIOPHYSICAL LOOKUP TABLES (THE CONSTANTS)
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
    'GLN': -3.5, 'ASP': -3.5, 'ASN': -3.5, 'LYS': -3.9, 'ARG': -4.5,
    # Alternate protonation/bonding states (same as parent residue)
    'HSD': -3.2, 'HSE': -3.2, 'HIP': -3.2,  # histidine variants
    'CYX': 2.5, 'CYM': 2.5,  # cysteine variants
}

# 2. Charge (pH 7.4)
CHARGE = {
    'ARG': 1, 'LYS': 1, 'HIS': 0.1, 
    'ASP': -1, 'GLU': -1,
    'ALA': 0, 'VAL': 0, 'LEU': 0, 'ILE': 0, 'MET': 0, 'PHE': 0, 'TRP': 0, 
    'PRO': 0, 'GLY': 0, 'SER': 0, 'THR': 0, 'CYS': 0, 'TYR': 0, 'ASN': 0, 'GLN': 0,
    # Alternate protonation/bonding states
    'HSD': 0, 'HSE': 0,  # neutral histidine (δ or ε protonated)
    'HIP': 1,  # doubly protonated histidine (positively charged)
    'CYX': 0,  # cysteine in disulfide bond (neutral)
    'CYM': -1,  # deprotonated cysteine (negatively charged thiolate)
}

# 3. Van der Waals Volume
VOLUME = {
    'GLY': 60.1, 'ALA': 88.6, 'SER': 89.0, 'CYS': 108.5, 'PRO': 112.7,
    'ASP': 111.1, 'THR': 116.1, 'ASN': 114.1, 'VAL': 140.0, 'GLU': 138.4,
    'GLN': 143.8, 'HIS': 153.2, 'MET': 162.9, 'ILE': 166.7, 'LEU': 166.7,
    'LYS': 168.6, 'ARG': 173.4, 'PHE': 189.9, 'TYR': 193.6, 'TRP': 227.8,
    # Alternate protonation/bonding states (same volume as parent residue)
    'HSD': 153.2, 'HSE': 153.2, 'HIP': 153.2,  # histidine variants
    'CYX': 108.5, 'CYM': 108.5,  # cysteine variants
}

def one_to_three(one_letter):
    return AA_MAP_1_TO_3.get(one_letter.upper())


def normalize_resname(name: str) -> str:
    """Normalize PDB residue names to standard 3-letter codes or recognized variants.
    
    Handles:
    - Case normalization (uppercase)
    - Selenomethionine (MSE -> MET)
    - Ambiguous residues (ASX -> ASP, GLX -> GLU)
    - Preserves alternate protonation states (HSD, HSE, HIP, CYX, CYM)
    """
    name = name.upper().strip()
    
    # Preserve recognized alternate states
    if name in ("HSD", "HSE", "HIP", "CYX", "CYM"):
        return name
    
    # Map non-standard to standard
    if name == "MSE":  # Selenomethionine
        return "MET"
    if name == "ASX":  # Ambiguous Asp/Asn
        return "ASP"
    if name == "GLX":  # Ambiguous Glu/Gln
        return "GLU"
    
    return name


def parse_variant_code(variant_code: str) -> tuple[str, int, str, str, str]:
    """Parses 'A53T' or 'Ala53Thr' -> (wt_1, pos, mut_1, wt_3, mut_3)."""
    import re
    
    # Try 1-letter format first: A53T
    match_1 = re.match(r"^([A-Z])(\d+)([A-Z])$", variant_code.upper())
    if match_1:
        wt_1, pos_str, mut_1 = match_1.groups()
        pos = int(pos_str)
        wt_3 = one_to_three(wt_1)
        mut_3 = one_to_three(mut_1)
        if not wt_3 or not mut_3:
            raise ValueError(f"Invalid amino acid code in variant '{variant_code}'.")
        return wt_1, pos, mut_1, wt_3, mut_3

    # Try 3-letter format: Ala53Thr
    match_3 = re.match(r"^([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})$", variant_code)
    if match_3:
        wt_3_raw, pos_str, mut_3_raw = match_3.groups()
        wt_3 = wt_3_raw.upper()
        mut_3 = mut_3_raw.upper()
        pos = int(pos_str)
        
        # Reverse lookup 3->1
        map_3_to_1 = {v: k for k, v in AA_MAP_1_TO_3.items()}
        wt_1 = map_3_to_1.get(wt_3)
        mut_1 = map_3_to_1.get(mut_3)
        
        if not wt_1 or not mut_1:
             raise ValueError(f"Invalid amino acid code in variant '{variant_code}'.")
             
        return wt_1, pos, mut_1, wt_3, mut_3

    raise ValueError("Invalid variant format. Use format like 'A53T' or 'Ala53Thr'.")


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


def _check_hbond_geometry(donor_atom, acceptor_atom, donor_heavy_atom) -> bool:
    """Check if D-H...A geometry is compatible with H-bonding (angle > 120°).
    
    Since PDB files often lack explicit hydrogens, we approximate:
    - Use donor heavy atom (N or O) as proxy for hydrogen direction
    - Check D...A distance < 3.5 Å (already done by caller)
    - Check D-heavy...A angle > 90° (relaxed from ideal 120° due to H approximation)
    
    Returns True if geometry permits H-bond.
    """
    try:
        # Vector from donor heavy atom to acceptor
        vec_donor_to_acceptor = acceptor_atom.get_coord() - donor_heavy_atom.get_coord()
        vec_donor_to_polar = donor_atom.get_coord() - donor_heavy_atom.get_coord()
        
        # Angle between D-heavy → D-polar and D-heavy → acceptor
        # If angle > 90°, geometry is reasonable for H-bond
        dot_product = np.dot(vec_donor_to_acceptor, vec_donor_to_polar)
        norm_product = np.linalg.norm(vec_donor_to_acceptor) * np.linalg.norm(vec_donor_to_polar)
        
        if norm_product < 1e-6:
            return False
        
        cos_angle = dot_product / norm_product
        angle_deg = np.degrees(np.arccos(np.clip(cos_angle, -1.0, 1.0)))
        
        # Relaxed criterion: angle > 90° (in practice, H would extend further)
        return angle_deg > 90.0
    except Exception:
        # If geometry check fails, conservatively assume H-bond possible
        return True


def _get_hbond_donors_acceptors(residue):
    """Extract H-bond donor and acceptor atoms from a residue.
    
    Returns: (donors, acceptors) where each is list of (atom, heavy_atom_reference)
    - donors: N-H groups (use N as heavy atom ref), O-H groups (use O)
    - acceptors: C=O groups (carbonyl O), O- groups (Asp/Glu), N (His)
    """
    donors = []
    acceptors = []
    resname = normalize_resname(residue.get_resname())
    
    # Backbone always has N-H donor and C=O acceptor
    if "N" in residue:
        donors.append((residue["N"], residue["CA"] if "CA" in residue else residue["N"]))
    if "O" in residue:
        acceptors.append((residue["O"], residue["C"] if "C" in residue else residue["O"]))
    
    # Side-chain donors/acceptors by residue type
    if resname in {"SER", "THR", "TYR"}:  # Hydroxyl groups (O-H donors and acceptors)
        if "OG" in residue:  # Ser
            donors.append((residue["OG"], residue["CB"] if "CB" in residue else residue["OG"]))
            acceptors.append((residue["OG"], residue["CB"] if "CB" in residue else residue["OG"]))
        if "OG1" in residue:  # Thr
            donors.append((residue["OG1"], residue["CB"] if "CB" in residue else residue["OG1"]))
            acceptors.append((residue["OG1"], residue["CB"] if "CB" in residue else residue["OG1"]))
        if "OH" in residue:  # Tyr
            donors.append((residue["OH"], residue["CZ"] if "CZ" in residue else residue["OH"]))
            acceptors.append((residue["OH"], residue["CZ"] if "CZ" in residue else residue["OH"]))
    
    if resname in {"ASN", "GLN"}:  # Amide groups (N-H donors, C=O acceptors)
        if resname == "ASN":
            if "OD1" in residue:
                acceptors.append((residue["OD1"], residue["CG"] if "CG" in residue else residue["OD1"]))
            if "ND2" in residue:
                donors.append((residue["ND2"], residue["CG"] if "CG" in residue else residue["ND2"]))
        elif resname == "GLN":
            if "OE1" in residue:
                acceptors.append((residue["OE1"], residue["CD"] if "CD" in residue else residue["OE1"]))
            if "NE2" in residue:
                donors.append((residue["NE2"], residue["CD"] if "CD" in residue else residue["NE2"]))
    
    if resname in {"ASP", "GLU"}:  # Carboxylate groups (O acceptors)
        if resname == "ASP":
            for atom_name in ["OD1", "OD2"]:
                if atom_name in residue:
                    acceptors.append((residue[atom_name], residue["CG"] if "CG" in residue else residue[atom_name]))
        elif resname == "GLU":
            for atom_name in ["OE1", "OE2"]:
                if atom_name in residue:
                    acceptors.append((residue[atom_name], residue["CD"] if "CD" in residue else residue[atom_name]))
    
    if resname in {"HIS", "HSD", "HSE", "HIP"}:  # Imidazole (N donors and acceptors)
        if "ND1" in residue:
            donors.append((residue["ND1"], residue["CG"] if "CG" in residue else residue["ND1"]))
            acceptors.append((residue["ND1"], residue["CG"] if "CG" in residue else residue["ND1"]))
        if "NE2" in residue:
            donors.append((residue["NE2"], residue["CD2"] if "CD2" in residue else residue["NE2"]))
            acceptors.append((residue["NE2"], residue["CD2"] if "CD2" in residue else residue["NE2"]))
    
    if resname in {"LYS", "ARG"}:  # Charged amines (N-H donors)
        if resname == "LYS" and "NZ" in residue:
            donors.append((residue["NZ"], residue["CE"] if "CE" in residue else residue["NZ"]))
        elif resname == "ARG":
            for atom_name in ["NE", "NH1", "NH2"]:
                if atom_name in residue:
                    donors.append((residue[atom_name], residue["CZ"] if "CZ" in residue else residue[atom_name]))
    
    if resname == "TRP" and "NE1" in residue:  # Indole N-H donor
        donors.append((residue["NE1"], residue["CD1"] if "CD1" in residue else residue["NE1"]))
    
    return donors, acceptors


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
        print(f"[WARN] DSSP Warning: {e}. (Is mkdssp installed?)")
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

    # Refined SASA exposure categories (literature-based thresholds)
    if sasa < 10:
        exposure = "Buried"  # Core residues, minimal solvent contact
    elif sasa < 40:
        exposure = "Partially Exposed"  # Surface-proximal, some solvent
    else:
        exposure = "Exposed"  # Fully solvent-accessible
    
    return {
        "chain": chain_id_resolved,
        "resseq": resseq,
        "resname": normalize_resname(residue.get_resname()),
        "sasa": round(float(sasa), 2),
        "exposure": exposure,
        "plddt_confidence": round(plddt, 2),
        "secondary_structure": sec_struct,
        "neighbor_residue_count_5A": int(neighbor_count),
    }

# ==========================================
# ️ INTERACTION ENGINE (Features 7, 8, 9)
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
        "salt_bridges_gained": [],
        "disulfides_lost": [],
        "disulfides_gained": [],
        "h_bonds_lost_est": 0,
        "h_bonds_gained_est": 0,
    }

    atoms = Bio.PDB.Selection.unfold_entities(model, "A")
    ns = NeighborSearch(atoms)

    # Broad neighbor search (sidechains can extend beyond CA distance).
    # UPDATED: Increased radius to 12.0Å to capture long side-chain interactions (e.g., Arg/Lys tips).
    center_atom = target_res["CA"] if "CA" in target_res else list(target_res)[-1]
    neighbor_residues = ns.search(center_atom.get_coord(), 12.0, level="R")

    # 7) Salt bridges: charged atom distance < 4.0Å
    positive = {"ARG", "LYS", "HIS", "HSD", "HSE", "HIP"}  # Include histidine variants
    negative = {"ASP", "GLU"}
    
    # LOSS: WT has charge, forms bridge, MUT loses it
    if wt_resname in positive or wt_resname in negative:
        my_atoms = CHARGED_ATOMS.get(wt_resname, [])
        for neighbor in neighbor_residues:
            if neighbor is target_res:
                continue
            neighbor_name = normalize_resname(neighbor.get_resname())
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
    
    # GAIN: WT neutral/opposite, MUT gains compatible charge
    if mut_resname in positive or mut_resname in negative:
        wt_is_neutral = wt_resname not in (positive | negative)
        wt_is_same_sign = (wt_resname in positive and mut_resname in positive) or (
            wt_resname in negative and mut_resname in negative
        )
        
        if wt_is_neutral or wt_is_same_sign:
            # MUT could form new bridges with oppositely charged neighbors
            for neighbor in neighbor_residues:
                if neighbor is target_res:
                    continue
                neighbor_name = normalize_resname(neighbor.get_resname())
                if neighbor_name not in (positive | negative):
                    continue
                
                # Check if MUT and neighbor have opposite charges
                mut_creates_bridge = (mut_resname in positive and neighbor_name in negative) or (
                    mut_resname in negative and neighbor_name in positive
                )
                if not mut_creates_bridge:
                    continue
                
                # Assume mutation preserves backbone geometry - use existing CA distance as proxy
                # If neighbor is within salt bridge range of WT CA, MUT could form bridge
                neighbor_atoms = CHARGED_ATOMS.get(neighbor_name, [])
                if neighbor_atoms and "CA" in target_res:
                    ca_dist = target_res["CA"] - neighbor["CA"] if "CA" in neighbor else float("inf")
                    # Conservative estimate: only flag if CAs are close enough for sidechain contact
                    if ca_dist < 8.0:  # Arg/Lys sidechains can extend ~6-7Å from CA
                        interactions["salt_bridges_gained"].append(f"{neighbor_name}{neighbor.id[1]}")

    # 8) Disulfides: SG-SG < 2.5Å
    cys_variants = {"CYS", "CYX"}  # Include disulfide-bonded cysteine
    
    # LOSS: WT is Cys with existing disulfide, MUT is not Cys
    if wt_resname in cys_variants and mut_resname not in cys_variants and "SG" in target_res:
        candidate_residues = ns.search(target_res["SG"].get_coord(), 3.5, level="R")
        for neighbor in candidate_residues:
            if neighbor is target_res:
                continue
            neighbor_name = normalize_resname(neighbor.get_resname())
            if neighbor_name not in cys_variants or "SG" not in neighbor:
                continue
            dist = target_res["SG"] - neighbor["SG"]
            if dist < 2.5:
                interactions["disulfides_lost"].append(f"{neighbor_name}{neighbor.id[1]}")
    
    # GAIN: WT is not Cys, MUT is Cys near another free Cys
    if mut_resname in cys_variants and wt_resname not in cys_variants and "CA" in target_res:
        # Check for nearby cysteines that could form new disulfide with mutant
        candidate_residues = ns.search(target_res["CA"].get_coord(), 8.0, level="R")
        for neighbor in candidate_residues:
            if neighbor is target_res:
                continue
            neighbor_name = normalize_resname(neighbor.get_resname())
            if neighbor_name not in cys_variants or "SG" not in neighbor:
                continue
            # Conservative estimate: CA-CA distance as proxy for potential SG-SG bond
            ca_dist = target_res["CA"] - neighbor["CA"] if "CA" in neighbor else float("inf")
            if ca_dist < 6.0:  # SG is ~2-3Å from CA, so 6Å CA-CA allows ~2.5Å SG-SG
                interactions["disulfides_gained"].append(f"{neighbor_name}{neighbor.id[1]}")

    # 9) H-bond loss/gain with geometry validation (distance + angle)
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
    
    # LOSS: WT is polar, MUT is not
    if wt_resname in polar_residues and mut_resname not in polar_residues:
        h_loss_count = 0
        wt_donors, wt_acceptors = _get_hbond_donors_acceptors(target_res)
        
        for neighbor in neighbor_residues:
            if neighbor is target_res:
                continue
            neighbor_donors, neighbor_acceptors = _get_hbond_donors_acceptors(neighbor)
            
            # Check WT as donor to neighbor as acceptor
            for wt_donor, wt_heavy in wt_donors:
                for neighbor_acceptor, neighbor_heavy in neighbor_acceptors:
                    dist = wt_donor - neighbor_acceptor
                    if dist < 3.5 and _check_hbond_geometry(wt_donor, neighbor_acceptor, wt_heavy):
                        h_loss_count += 1
                        break
            
            # Check WT as acceptor to neighbor as donor
            for wt_acceptor, wt_heavy in wt_acceptors:
                for neighbor_donor, neighbor_heavy in neighbor_donors:
                    dist = neighbor_donor - wt_acceptor
                    if dist < 3.5 and _check_hbond_geometry(neighbor_donor, wt_acceptor, neighbor_heavy):
                        h_loss_count += 1
                        break
        
        interactions["h_bonds_lost_est"] = h_loss_count
    
    # GAIN: WT is not polar, MUT is polar (approximate based on backbone + sidechain reach)
    if mut_resname in polar_residues and wt_resname not in polar_residues:
        h_gain_count = 0
        # Estimate MUT H-bond potential: backbone stays, sidechain extends ~4-6Å from CA
        if "CA" in target_res:
            # Get MUT's expected donor/acceptor capacity (we know the residue type)
            # Use a dummy residue to get D/A profile
            mut_has_donors = mut_resname in {"SER", "THR", "TYR", "ASN", "GLN", "HIS", "TRP", "LYS", "ARG"}
            mut_has_acceptors = mut_resname in {"SER", "THR", "TYR", "ASN", "GLN", "ASP", "GLU", "HIS"}
            
            for neighbor in neighbor_residues:
                if neighbor is target_res:
                    continue
                neighbor_donors, neighbor_acceptors = _get_hbond_donors_acceptors(neighbor)
                
                # Check if MUT could donate to neighbor acceptors
                if mut_has_donors:
                    for neighbor_acceptor, _ in neighbor_acceptors:
                        ca_dist = target_res["CA"] - neighbor_acceptor
                        # Sidechain can extend ~6Å, so if acceptor within 7Å of CA, H-bond possible
                        if ca_dist < 7.0:
                            h_gain_count += 1
                            break
                
                # Check if MUT could accept from neighbor donors
                if mut_has_acceptors:
                    for neighbor_donor, _ in neighbor_donors:
                        ca_dist = target_res["CA"] - neighbor_donor
                        if ca_dist < 7.0:
                            h_gain_count += 1
                            break
        
        interactions["h_bonds_gained_est"] = h_gain_count

    return interactions

# ==========================================
#  MAIN ANALYSIS LOGIC (Features 1-10)
# ==========================================
def analyze_protein(pdb_path, variant_code, *, chain_id: str | None = None, verbose: bool = True):
    chain_label = chain_id if chain_id is not None else "<first>"
    if verbose:
        print(f"--- >> ANALYZING {variant_code} (chain {chain_label}) ---")
    
    # A. Parse Variant
    try:
        _wt_1, res_id, _mut_1, wt_3, mut_3 = parse_variant_code(variant_code)
        wt_3 = normalize_resname(wt_3)
        mut_3 = normalize_resname(mut_3)
    except ValueError as e:
        print(f"[ERROR] {e}")
        return None
    
    # B. Load Structure
    structure = load_structure(pdb_path)
    model = structure[0]
    chain = get_chain(model, chain_id)
    target_res = find_residue_by_resseq(chain, res_id)
    if target_res is None:
        print(f"[ERROR] Error: Residue {res_id} not found in PDB.")
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
    wt_volume = _as_float_or_none(VOLUME.get(wt_3, 0))
    mut_volume = _as_float_or_none(VOLUME.get(mut_3, 0))
    wt_hydro = _as_float_or_none(HYDROPHOBICITY.get(wt_3, 0))
    mut_hydro = _as_float_or_none(HYDROPHOBICITY.get(mut_3, 0))
    wt_charge = _as_float_or_none(CHARGE.get(wt_3, 0))
    mut_charge = _as_float_or_none(CHARGE.get(mut_3, 0))

    # Refined exposure classification
    if sasa < 10:
        exposure = "Buried"
    elif sasa < 40:
        exposure = "Partially Exposed"
    else:
        exposure = "Exposed"
    
    comparison_view = {
        "residue": {"wt": wt_3, "mut": mut_3, "delta": None},
        "volume": {"wt": wt_volume, "mut": mut_volume, "delta": round(float(d_vol), 2)},
        "hydrophobicity": {"wt": wt_hydro, "mut": mut_hydro, "delta": round(float(d_hydro), 2)},
        "charge": {"wt": wt_charge, "mut": mut_charge, "delta": float(d_charge)},
        # Structural context is only available for WT in virtual-swap mode.
        "sasa": {"wt": round(float(sasa), 2), "mut": None, "delta": None},
        "plddt_confidence": {"wt": round(float(plddt), 2), "mut": None, "delta": None},
        "secondary_structure": {"wt": sec_struct, "mut": None, "delta": None},
        "exposure": {"wt": exposure, "mut": None, "delta": None},
    }

    result = {
        "variant": variant_code,
        "comparison_view": comparison_view,
        "wild_type": {
            "residue": wt_3,
            "volume": wt_volume,
            "hydrophobicity": wt_hydro,
            "charge": wt_charge,
        },
        "mutant_properties": {
            "residue": mut_3,
            "volume": mut_volume,
            "hydrophobicity": mut_hydro,
            "charge": mut_charge,
        },
        "deltas": {
            "delta_volume": round(d_vol, 2),
            "delta_hydrophobicity": round(d_hydro, 2),
            "delta_charge": d_charge
        },
        "structural_context_wt": {
            "sasa": round(sasa, 2),
            "exposure": exposure,
            "secondary_structure": sec_struct,
            "plddt_confidence": round(plddt, 2)
        },
        "stability_audit": {
            "salt_bridges_lost": interaction_data['salt_bridges_lost'],
            "salt_bridges_gained": interaction_data['salt_bridges_gained'],
            "disulfides_lost": interaction_data['disulfides_lost'],
            "disulfides_gained": interaction_data['disulfides_gained'],
            "h_bonds_lost_est": interaction_data['h_bonds_lost_est'],
            "h_bonds_gained_est": interaction_data['h_bonds_gained_est'],
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

    wt_volume = _as_float_or_none(VOLUME.get(wt_3, 0))
    mut_volume = _as_float_or_none(VOLUME.get(mut_3, 0))
    wt_hydro = _as_float_or_none(HYDROPHOBICITY.get(wt_3, 0))
    mut_hydro = _as_float_or_none(HYDROPHOBICITY.get(mut_3, 0))
    wt_charge = _as_float_or_none(CHARGE.get(wt_3, 0))
    mut_charge = _as_float_or_none(CHARGE.get(mut_3, 0))

    comparison_view = {
        "residue": {"wt": wt_3, "mut": mut_3, "delta": None},
        "volume": {"wt": wt_volume, "mut": mut_volume, "delta": round(float(d_vol), 2)},
        "hydrophobicity": {"wt": wt_hydro, "mut": mut_hydro, "delta": round(float(d_hydro), 2)},
        "charge": {"wt": wt_charge, "mut": mut_charge, "delta": float(d_charge)},
        "sasa": {"wt": wt_metrics["sasa"], "mut": mut_metrics["sasa"], "delta": observed_deltas["delta_sasa"]},
        "plddt_confidence": {
            "wt": wt_metrics["plddt_confidence"],
            "mut": mut_metrics["plddt_confidence"],
            "delta": observed_deltas["delta_plddt_confidence"],
        },
        "neighbor_residue_count_5A": {
            "wt": wt_metrics["neighbor_residue_count_5A"],
            "mut": mut_metrics["neighbor_residue_count_5A"],
            "delta": observed_deltas["delta_neighbor_residue_count_5A"],
        },
        "secondary_structure": {
            "wt": wt_metrics["secondary_structure"],
            "mut": mut_metrics["secondary_structure"],
            "delta": "CHANGED" if observed_deltas["secondary_structure_changed"] else "Same",
        },
        "exposure": {
            "wt": wt_metrics["exposure"],
            "mut": mut_metrics["exposure"],
            "delta": None,
        },
    }

    return {
        "variant": variant_code,
        "position": resseq,
        "comparison_view": comparison_view,
        "wild_type": {
            "residue": wt_3,
            "volume": wt_volume,
            "hydrophobicity": wt_hydro,
            "charge": wt_charge,
            "pdb": wt_pdb_path,
            "site_metrics": wt_metrics,
        },
        "mutant": {
            "residue": mut_3,
            "volume": mut_volume,
            "hydrophobicity": mut_hydro,
            "charge": mut_charge,
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
    # Keep pipeline output clean; CLI printing happens in __main__.
    return analyze_protein(pdb_path, variant_code, chain_id=chain_id, verbose=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze intrinsic residue deltas and (optionally) WT-vs-MUT structural deltas.")
    parser.add_argument("pdb", nargs="?", help="Path to PDB file (single-structure mode)")
    parser.add_argument("variant", nargs="?", help="Mutation code (e.g. V50M)")
    parser.add_argument("--wt-pdb", help="WT PDB path (compare mode)", default=None)
    parser.add_argument("--mut-pdb", help="Mutant PDB path (compare mode)", default=None)
    parser.add_argument("--chain-wt", help="WT chain ID (compare mode)", default=None)
    parser.add_argument("--chain-mut", help="Mutant chain ID (compare mode)", default=None)
    parser.add_argument("--chain", help="Chain ID (single-structure mode; default: first chain)", default=None)
    parser.add_argument(
        "--analysis-out-dir",
        help="Directory to save JSON output (default: data/analysis)",
        default="data/analysis",
    )
    parser.add_argument("--out", help="Output JSON path (default: <variant>_analysis.json)", default=None)
    parser.add_argument("--no-table", action="store_true", help="Do not print side-by-side comparison table")
    args = parser.parse_args()

    if args.wt_pdb or args.mut_pdb:
        if not args.wt_pdb or not args.mut_pdb or not args.variant:
            print("[ERROR] Compare mode requires --wt-pdb, --mut-pdb, and <variant>.")
            sys.exit(2)
        data = analyze_variant_pair(args.wt_pdb, args.mut_pdb, args.variant, chain_wt=args.chain_wt, chain_mut=args.chain_mut)
        if args.out:
            out_file = args.out
        else:
            base_name = os.path.basename(args.wt_pdb).replace(".pdb", "")
            os.makedirs(args.analysis_out_dir, exist_ok=True)
            out_file = os.path.join(args.analysis_out_dir, f"{base_name}_{args.variant}_compare.json")
    else:
        if not args.pdb or not args.variant:
            print("[ERROR] Single-structure mode requires <pdb> <variant>.")
            sys.exit(2)
        data = analyze_protein(args.pdb, args.variant, chain_id=args.chain, verbose=True)
        out_file = args.out or _default_physics_json_path(args.pdb, args.variant, out_dir=args.analysis_out_dir)

    if data and (not args.no_table):
        cv = data.get("comparison_view")
        if isinstance(cv, dict):
            _print_comparison_table(cv, title="\nComparison View (WT vs MUT vs Δ)")

    with open(out_file, "w") as f:
        json.dump(data, f, indent=4)
    print(f"[OK] Analysis saved to {out_file}")


# ==========================================
# >> 10 BIOPHYSICAL FEATURES & NEURODEGENERATION RISK
# ==========================================
"""
HOW EACH FEATURE CONTRIBUTES TO NEURODEGENERATIVE DISEASE RISK:

1. VOLUME CHANGE (Δ Volume)
   - What it measures: How much bigger or smaller the mutant amino acid is compared to wild-type
   - Disease risk: Large changes can cause protein misfolding. Example: A small-to-large mutation 
     creates steric clashes that destabilize the protein, leading to aggregation (a hallmark of 
     Alzheimer's, Parkinson's, ALS)

2. HYDROPHOBICITY CHANGE (Δ Hydrophobicity)
   - What it measures: Whether the mutation makes the site more water-loving or water-hating
   - Disease risk: Exposing hydrophobic residues to water (or burying hydrophilic ones) causes 
     misfolding. Misfolded proteins stick together forming toxic aggregates (amyloid plaques, 
     Lewy bodies, TDP-43 inclusions)

3. CHARGE CHANGE (Δ Charge)
   - What it measures: Gain or loss of positive/negative charge
   - Disease risk: Losing a charge can break critical salt bridges that hold the protein together. 
     Gaining the wrong charge can cause electrostatic repulsion, leading to unfolding and aggregation

4. SASA (Solvent Accessible Surface Area)
   - What it measures: Whether the mutation site is buried inside the protein or exposed on the surface
   - Disease risk: Buried sites are more sensitive to mutations because any change disrupts the tightly 
     packed core. Core destabilization → misfolding → aggregation. Surface mutations are usually 
     better tolerated unless they affect binding sites

5. SECONDARY STRUCTURE
   - What it measures: Whether the site is in an alpha helix, beta sheet, or loop
   - Disease risk: Mutations in structured regions (helices/sheets) are more likely to disrupt folding. 
     Beta-sheet mutations are especially dangerous because they can promote conversion to amyloid 
     (the fibrillar form seen in plaques)

6. pLDDT (AlphaFold Confidence)
   - What it measures: How confident AlphaFold is about the local structure (high = rigid, low = flexible)
   - Disease risk: Low-confidence regions are intrinsically disordered. Mutations here can shift the 
     protein toward aggregation-prone conformations. Many neurodegenerative proteins (alpha-synuclein, 
     tau) have disordered regions that are mutation hotspots

7. SALT BRIDGES LOST
   - What it measures: How many ionic bonds (positive-negative pairs) are broken by the mutation
   - Disease risk: Salt bridges are critical for protein stability. Losing them causes unfolding, 
     which exposes sticky hydrophobic patches that drive aggregation

8. DISULFIDE BONDS LOST
   - What it measures: Whether a cysteine-cysteine bridge (S-S bond) is broken
   - Disease risk: Disulfide bonds act as molecular staples. Breaking them destabilizes the structure, 
     making the protein prone to aggregation. SOD1 (ALS) has critical disulfides

9. HYDROGEN BONDS LOST (Estimate)
   - What it measures: How many polar contacts are lost if a polar residue becomes non-polar
   - Disease risk: Hydrogen bonds fine-tune protein structure. Losing multiple H-bonds weakens the 
     protein scaffold, increasing misfolding risk. This is cumulative damage

10. BACKBONE STRAIN
    - What it measures: Whether the mutation creates geometric stress (Glycine flexibility loss, 
      Proline helix-breaking)
    - Disease risk: Backbone strain forces the protein into unnatural conformations. These stressed 
      states are thermodynamically unstable and more likely to misfold or trigger quality control 
      pathways (ER stress, proteasome overload) that eventually kill neurons

KEY INSIGHT:
Neurodegenerative diseases share a common mechanism: protein aggregation. A single mutation rarely 
causes disease through one feature alone. Instead, mutations accumulate risk across multiple features 
(e.g., losing salt bridges + exposing hydrophobic core + high aggregation propensity). This pipeline 
quantifies that cumulative burden.

"""
