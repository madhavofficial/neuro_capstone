import sys
import json
import os
import argparse
import re
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Force UTF-8 encoding for stdout
if sys.stdout.encoding is None or sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

class NLPFormationError(Exception):
    """Custom exception for NLP query formation failures."""
    pass

def load_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        raise NLPFormationError(f"Failed to load JSON from {path}: {e}")

def extract_signals(physics):
    """
    Extracts structured metrics safely from JSON dicts.
    """
    variant = physics.get("variant", "")
    # Robust Regex: WT(A-Z), Pos(0-9), MUT(A-Z)
    m = re.match(r"([A-Za-z]+)(\d+)([A-Za-z*]+)", variant)
    if m:
        wt, pos, mut = m.groups()
    else:
        # Fallback if unparseable
        logger.warning(f"Could not parse variant string: {variant}. Using placeholders.")
        wt, pos, mut = "?", variant[3:] if len(variant) > 3 else "?", "?"
    
    comp_view = physics.get("comparison_view", {})
    wt_residue = comp_view.get("residue", {}).get("wt", wt)
    mut_residue = comp_view.get("residue", {}).get("mut", mut)
    
    deltas = physics.get("deltas", {})
    
    def _safe_float(val, default=0.0):
        if val is None:
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    delta_vol = _safe_float(deltas.get("delta_volume"))
    delta_hydro = _safe_float(deltas.get("delta_hydrophobicity"))
    delta_charge = _safe_float(deltas.get("delta_charge"))
    
    wt_context = physics.get("structural_context_wt", {})
    exposure = wt_context.get("exposure", "Unknown")
    sasa = _safe_float(wt_context.get("sasa"))
    
    sec_struct = wt_context.get("secondary_structure", "Unknown")
    plddt = _safe_float(wt_context.get("plddt_confidence"), 100.0)
    
    stability_audit = physics.get("stability_audit", {})
    h_bonds_lost = stability_audit.get("h_bonds_lost_est", 0)
    if not isinstance(h_bonds_lost, (int, float)):
        h_bonds_lost = 0

    return {
        "variant": variant,
        "pos": pos,
        "wt": wt_residue,
        "mut": mut_residue,
        "delta_vol": delta_vol,
        "delta_hydro": delta_hydro,
        "delta_charge": delta_charge,
        "exposure": exposure,
        "sasa": sasa,
        "sec_struct": sec_struct,
        "plddt": plddt,
        "h_bonds_lost": int(h_bonds_lost),
    }

def interpret_and_prioritize(signals):
    """
    Evaluates physical signals under structural context to determine biological consequence.
    Applies Context-Aware Weighting and Signal Prioritization.
    Returns list of highest priority mechanisms.
    """
    mechanisms = [] # stored as (priority_score, string) -> HIGHER score = MORE important
    
    # --- 1. Volume Changes (Context-Aware Weighting) ---
    dV = signals["delta_vol"]
    exposure = signals["exposure"]
    sasa = signals["sasa"]
    
    if exposure == "Buried" or sasa < 15.0:
        if dV > 30:
            mechanisms.append((10, f"potential severe steric strain disrupting core packing (ΔV={dV:+.1f})"))
        elif dV > 10:
            mechanisms.append((7, f"potential mild internal steric crowding (ΔV={dV:+.1f})"))
        elif dV < -30:
            mechanisms.append((9, f"internal cavity creation suggesting potential destabilization (ΔV={dV:+.1f})"))
    else:  # Exposed
        if dV > 25:
            mechanisms.append((5, f"surface structural alteration affecting interaction interfaces (ΔV={dV:+.1f})"))
        elif dV < -40:
            mechanisms.append((3, f"potential minor surface cavity creation (ΔV={dV:+.1f})"))

    # --- 2. Hydrophobic Core & Surface Changes ---
    dH = signals["delta_hydro"]
    if exposure == "Buried" and dH < -1.0:
        mechanisms.append((11, f"potential disruption of the hydrophobic core (Δhydrophobicity={dH:+.1f})"))
    elif exposure == "Exposed" and dH > 1.0:
        sasa_note = " highly solvent-accessible" if sasa > 50 else ""
        mechanisms.append((9, f"aberrant surface hydrophobicity on a{sasa_note} region, potentially increasing aggregation propensity"))
    elif exposure == "Exposed" and dH < -1.0:
        mechanisms.append((6, f"introduction of a polar/hydrophilic residue (Δhydrophobicity={dH:+.1f}) potentially altering surface interactions"))

    # --- 3. pLDDT (AlphaFold Disorder Guidelines) & Secondary Structure ---
    plddt = signals["plddt"]
    if plddt < 50:
        mechanisms.append((8, f"occurrence within a highly disordered region (pLDDT={plddt:.1f})"))
    elif plddt < 70:
        mechanisms.append((6, f"localization within a flexible or low-confidence structurally dynamic region (pLDDT={plddt:.1f})"))
    elif signals["sec_struct"] == "Loop":
        mechanisms.append((4, f"potential alteration of a flexible structural loop"))

    # --- 4. Charge Shifts ---
    dC = signals["delta_charge"]
    if dC != 0:
        if exposure == "Exposed":
            mechanisms.append((6, f"electrostatic surface shift (Δcharge={dC:+.1f}) potentially affecting binding/solubility"))
        else:
            mechanisms.append((10, f"buried charge alteration (Δcharge={dC:+.1f}) implying possible unfolding or destabilization"))

    # --- 5. Stability Audit (H-Bonds) ---
    if signals["h_bonds_lost"] > 0:
        mechanisms.append((9, f"potential localized destabilization via loss of {signals['h_bonds_lost']} estimated hydrogen bond(s)"))

    # Prioritize and filter to reduce noise (keep top 3 most important features based on score)
    mechanisms.sort(key=lambda x: x[0], reverse=True)
    top_mechanisms = [m[1] for m in mechanisms[:3]]
    
    return top_mechanisms

def construct_query(signals, mechanisms):
    """
    RAG-optimized syntactic synthesis of interpreted mechanisms.
    """
    if not mechanisms:
        core_query = f"Substitution {signals['variant']} ({signals['wt']}→{signals['mut']} at {signals['pos']}) with ambiguous structural impact."
    else:
        if len(mechanisms) > 2:
            mech_str = ", ".join(mechanisms[:-1]) + ", and " + mechanisms[-1]
        elif len(mechanisms) == 2:
            mech_str = " and ".join(mechanisms)
        else:
            mech_str = mechanisms[0]
        core_query = f"The {signals['wt']}→{signals['mut']} substitution at position {signals['pos']} suggests {mech_str}."

    query_parts = [core_query]

    # RAG Expansion Vocabulary (Injection of Synonyms based on signals)
    mech_text = " ".join(mechanisms).lower()
    
    primary_kws = []
    if "aggregation" in mech_text or "hydrophobicity" in mech_text:
        primary_kws.extend(["misfolding", "amyloidogenesis", "fibrillation"])
    if "steric" in mech_text or "cavity" in mech_text or "destabilization" in mech_text or "alteration affecting" in mech_text:
        primary_kws.extend(["conformational change", "protein destabilization", "structural strain"])
        
    disorder = "disordered" in mech_text or "flexible" in mech_text
    
    if primary_kws:
        # Keep top 3 varied keywords to avoid stuffing
        unique_kws = list(dict.fromkeys(primary_kws))[:3]
        if len(unique_kws) > 1:
            kw_str = ", ".join(unique_kws[:-1]) + ", and " + unique_kws[-1]
        else:
            kw_str = unique_kws[0]
            
        sentence = f"These predicted molecular consequences are linked to {kw_str}"
        if disorder:
            sentence += ", particularly within intrinsically disordered regions modifying functional dynamics."
        else:
            sentence += "."
        query_parts.append(sentence)
    elif disorder:
        query_parts.append("These predicted molecular consequences are linked to intrinsically disordered regions modifying functional dynamics.")

    return " ".join(query_parts)

def create_nlp_query(physics):
    """Entry point for dictionary-based physics input."""
    signals = extract_signals(physics)
    mechanisms = interpret_and_prioritize(signals)
    return construct_query(signals, mechanisms)

def create_nlp_query_from_file(physics_path):
    """Loads physics JSON and generates query."""
    if not os.path.exists(physics_path):
        raise NLPFormationError(f"Missing physics file: {physics_path}")
    physics = load_json(physics_path)
    return create_nlp_query(physics)

def run_nlp_formation(gene, variant, data_dir="data"):
    """
    Exportable function to generate NLP query for a specific gene/variant.
    
    Args:
        gene: Gene symbol
        variant: Variant code
        data_dir: Base directory for data
        
    Returns:
        The generated NLP query string
    """
    base = f"{gene}_{variant}"
    physics_path = os.path.join(data_dir, "analysis", f"{base}_physics.json")
    output_dir = os.path.join(data_dir, "NLP queries")
    output_path = os.path.join(output_dir, f"{base}_query.txt")

    logger.info(f"Generating NLP query for {gene} {variant}...")
    query = create_nlp_query_from_file(physics_path)
    
    os.makedirs(output_dir, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(query)
    
    logger.info(f"NLP query saved to {output_path}")
    return query

def main():
    parser = argparse.ArgumentParser(description="Generate NLP query via semantic translation of Physics/Context signals.")
    parser.add_argument("gene", help="Gene symbol, e.g. SNCA")
    parser.add_argument("variant", help="Variant code, e.g. A53T")
    parser.add_argument("--data-dir", default="data", help="Base data directory")
    args = parser.parse_args()

    try:
        query = run_nlp_formation(args.gene, args.variant, args.data_dir)
        print(f"\n{query}")
        return 0
    except Exception as e:
        logger.error(f"NLP Formation failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())

