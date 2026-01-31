import Bio.PDB
from Bio.PDB import PDBParser, ShrakeRupley
# REMOVED BROKEN IMPORT: from Bio.PDB.Polypeptide import three_to_one, one_to_three
import argparse
import os
import json
import sys
import numpy as np
import warnings

# Suppress Biopython PDB warnings
warnings.filterwarnings('ignore')

# ==========================================
# 🔧 UTILITIES (Fixed for Biopython 1.80+)
# ==========================================
# We define these manually to avoid import errors in newer Biopython versions.
AA_MAP_1_TO_3 = {
    'A': 'ALA', 'R': 'ARG', 'N': 'ASN', 'D': 'ASP', 'C': 'CYS',
    'Q': 'GLN', 'E': 'GLU', 'G': 'GLY', 'H': 'HIS', 'I': 'ILE',
    'L': 'LEU', 'K': 'LYS', 'M': 'MET', 'F': 'PHE', 'P': 'PRO',
    'S': 'SER', 'T': 'THR', 'W': 'TRP', 'Y': 'TYR', 'V': 'VAL'
}

def one_to_three(one_letter_code):
    """Converts 'V' to 'VAL'. Returns None if invalid."""
    return AA_MAP_1_TO_3.get(one_letter_code.upper())

# ==========================================
# 🧪 BIOPHYSICAL LOOKUP TABLES
# ==========================================

# 1. KYTE-DOOLITTLE (Hydrophobicity) - Positive = Sticky/Buried
# Source: J. Mol. Biol. 157:105-132 (1982)
HYDROPHOBICITY = {
    'ILE': 4.5, 'VAL': 4.2, 'LEU': 3.8, 'PHE': 2.8, 'CYS': 2.5,
    'MET': 1.9, 'ALA': 1.8, 'GLY': -0.4, 'THR': -0.7, 'SER': -0.8,
    'TRP': -0.9, 'TYR': -1.3, 'PRO': -1.6, 'HIS': -3.2, 'GLU': -3.5,
    'GLN': -3.5, 'ASP': -3.5, 'ASN': -3.5, 'LYS': -3.9, 'ARG': -4.5
}

# 2. CHARGE (pH 7.4)
CHARGE = {
    'ARG': 1, 'LYS': 1, 'HIS': 0.1, 
    'ASP': -1, 'GLU': -1,
    'ALA': 0, 'VAL': 0, 'LEU': 0, 'ILE': 0, 'MET': 0, 'PHE': 0, 'TRP': 0, 
    'PRO': 0, 'GLY': 0, 'SER': 0, 'THR': 0, 'CYS': 0, 'TYR': 0, 'ASN': 0, 'GLN': 0
}

# 3. VAN DER WAALS VOLUME (Angstroms^3) - Detects Steric Clashes
# Source: Richards, F.M. (1974)
VOLUME = {
    'GLY': 60.1, 'ALA': 88.6, 'SER': 89.0, 'CYS': 108.5, 'PRO': 112.7,
    'ASP': 111.1, 'THR': 116.1, 'ASN': 114.1, 'VAL': 140.0, 'GLU': 138.4,
    'GLN': 143.8, 'HIS': 153.2, 'MET': 162.9, 'ILE': 166.7, 'LEU': 166.7,
    'LYS': 168.6, 'ARG': 173.4, 'PHE': 189.9, 'TYR': 193.6, 'TRP': 227.8
}

# 4. CHOU-FASMAN (Beta-Sheet Propensity) - Higher = Amyloid Risk
# Source: Chou & Fasman (1978)
BETA_PROPENSITY = {
    'VAL': 1.70, 'ILE': 1.60, 'TYR': 1.47, 'PHE': 1.38, 'TRP': 1.37,
    'LEU': 1.30, 'CYS': 1.19, 'THR': 1.19, 'GLN': 1.10, 'MET': 1.05,
    'ARG': 0.93, 'ASN': 0.89, 'HIS': 0.87, 'ALA': 0.83, 'SER': 0.75,
    'GLY': 0.75, 'LYS': 0.74, 'ASP': 0.54, 'GLU': 0.37, 'PRO': 0.55
}

# ==========================================
# ⚙️ ENGINE LOGIC
# ==========================================

def calculate_physics_metrics(pdb_path, variant_code):
    print(f"\n--- ⚛️  STARTING PHYSICS ANALYSIS: {variant_code} ---")
    
    # 1. Parse Variant (e.g., "V50M")
    import re
    match = re.match(r"([A-Z])(\d+)([A-Z])", variant_code.upper())
    if not match:
        print("❌ Invalid variant format. Use format 'A53T'.")
        return None
    
    wt_aa_code, pos, mut_aa_code = match.groups()
    residue_id = int(pos)
    
    # Convert 1-letter to 3-letter (e.g., 'V' -> 'VAL')
    try:
        wt_aa = one_to_three(wt_aa_code)
        mut_aa = one_to_three(mut_aa_code)
    except KeyError:
        print(f"❌ Invalid Amino Acid code in {variant_code}")
        return None

    # 2. Load Structure
    print(f"   📂 Loading PDB: {pdb_path}")
    parser = PDBParser(QUIET=True)
    try:
        structure = parser.get_structure('protein', pdb_path)
    except Exception as e:
        print(f"   ❌ Error reading PDB: {e}")
        return None

    # 3. Locate Residue
    # AlphaFold/ESMFold usually put the main chain in Model 0, Chain A
    model = structure[0]
    chain = next(model.get_chains()) # Grab first chain
    
    # Biopython residues are indexed by (HeteroFlag, SequenceID, InsertCode)
    target_res = None
    for res in chain:
        if res.id[1] == residue_id:
            target_res = res
            break
            
    if not target_res:
        print(f"   ❌ Residue {residue_id} not found in structure. (Check numbering?)")
        return None

    res_name = target_res.get_resname() 
    print(f"   📍 Located Residue {residue_id}: {res_name}")

    # Sanity Check: Does the PDB match the Variant?
    # Note: AlphaFold DB usually has Wild Type. ESMFold might have Mutant.
    # We proceed regardless but log the state.
    if res_name != wt_aa and res_name != mut_aa:
        print(f"   ⚠️  Warning: PDB residue ({res_name}) matches neither WT ({wt_aa}) nor Mut ({mut_aa}).")

    # 4. Calculate SASA (Solvent Accessible Surface Area)
    print("   🧮 Running Geometry Engine (SASA)...")
    try:
        sr = ShrakeRupley()
        sr.compute(structure, level="R") 
        sasa = target_res.sasa
    except Exception as e:
        print(f"   ⚠️ SASA Calculation failed: {e}. Defaulting to 0.")
        sasa = 0.0
    
    # < 15 A^2 is Buried, > 15 A^2 is Exposed
    exposure_status = "Buried" if sasa < 15 else "Exposed"

    # 5. Calculate pLDDT (Confidence / Disorder)
    # AlphaFold stores pLDDT in the B-factor column
    plddt = 0.0
    atom_count = 0
    for atom in target_res:
        plddt += atom.bfactor
        atom_count += 1
    avg_plddt = plddt / atom_count if atom_count > 0 else 0
    
    # 6. Calculate DELTA (Change) Parameters
    # We compare the NEW amino acid (Mutant) vs the OLD (Wild Type)
    
    # A. Volume Change (Steric Strain)
    vol_wt = VOLUME.get(wt_aa, 0)
    vol_mut = VOLUME.get(mut_aa, 0)
    delta_vol = vol_mut - vol_wt
    
    # B. Hydrophobicity Change (Sticky Patch)
    hydro_wt = HYDROPHOBICITY.get(wt_aa, 0)
    hydro_mut = HYDROPHOBICITY.get(mut_aa, 0)
    delta_hydro = hydro_mut - hydro_wt
    
    # C. Charge Change
    charge_wt = CHARGE.get(wt_aa, 0)
    charge_mut = CHARGE.get(mut_aa, 0)
    delta_charge = charge_mut - charge_wt
    
    # D. Beta Propensity Change
    beta_wt = BETA_PROPENSITY.get(wt_aa, 0)
    beta_mut = BETA_PROPENSITY.get(mut_aa, 0)
    delta_beta = beta_mut - beta_wt

    # 7. Aggregation Logic (The "Verdict")
    # Rule 1: Exposed + Hydrophobic Increase = Aggregation Risk
    risk_aggregation = (delta_hydro > 0) and (sasa > 15)
    
    # Rule 2: Buried + Volume Increase = Destabilization/Explosion Risk
    risk_stability = (delta_vol > 20) and (sasa < 15)
    
    # Rule 3: Charge Loss = Solubility Risk
    risk_solubility = (delta_charge != 0)

    # 8. Compile Results
    physics_data = {
        "variant": variant_code,
        "position": residue_id,
        "metrics": {
            "sasa": round(sasa, 2),
            "exposure_status": exposure_status,
            "plddt": round(avg_plddt, 2),
            "delta_volume": round(delta_vol, 2),
            "delta_hydrophobicity": round(delta_hydro, 2),
            "delta_charge": round(delta_charge, 2),
            "delta_beta_propensity": round(delta_beta, 2)
        },
        "molecular_mechanisms": {
            "aggregation_risk": bool(risk_aggregation),
            "steric_clash_risk": bool(risk_stability),
            "solubility_risk": bool(risk_solubility)
        }
    }
    
    # Print Report
    print(f"\n   📊 ANALYSIS REPORT:")
    print(f"   -------------------")
    print(f"   Exposure:      {sasa:.2f} Å² ({exposure_status})")
    print(f"   Volume Δ:      {delta_vol:+.2f} Å³  {'[STERIC CLASH WARNING]' if risk_stability else ''}")
    print(f"   Hydrophobic Δ: {delta_hydro:+.2f}   {'[STICKY PATCH WARNING]' if risk_aggregation else ''}")
    print(f"   Charge Δ:      {delta_charge:+.2f}")
    print(f"   Beta Prop Δ:   {delta_beta:+.2f}")
    
    return physics_data

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdb_file", type=str, help="Path to PDB file")
    parser.add_argument("--variant", type=str, required=True, help="Mutation (e.g. V50M)")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.pdb_file):
        print("❌ PDB file not found.")
        sys.exit(1)
        
    results = calculate_physics_metrics(args.pdb_file, args.variant)
    
    # Save to JSON
    if results:
        # Save alongside the PDB file
        dir_name = os.path.dirname(args.pdb_file)
        base_name = os.path.basename(args.pdb_file).replace(".pdb", "")
        out_path = os.path.join(dir_name, f"{base_name}_{args.variant}_physics.json")
        
        with open(out_path, "w") as f:
            json.dump(results, f, indent=4)
        print(f"\n✅ Physics Analysis saved to: {out_path}")
"""
	•	Hydrophobicity (ΔH): Indicates how much stickier the mutated residue becomes, affecting aggregation risk.
	•	SASA (Local Exposure): Shows whether the mutated residue is buried or exposed, determining if its effects interact with solvent.
	•	Global SASA: Reflects overall protein surface openness, useful for comparing whole-protein packing.
	•	Net Charge (ΔQ): Reveals loss or gain of electrostatic repulsion, affecting solubility and stability.
	•	Residue Volume (ΔVol): Detects steric clashes by measuring if the new residue is too large for its local pocket.
	•	Beta-Sheet Propensity (Δβ): Shows increased tendency to form amyloid fibrils through β-sheet formation.
	•	pLDDT / Confiden    ce: Identifies disorder or structural uncertainty at the mutation site, key for misfolding susceptibility.
"""