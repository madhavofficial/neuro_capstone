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


# ── LLM system-prompt directive ───────────────────────────────────────────────
# Re-exported here so LLM controller code can import from a single, stable
# location.  The authoritative definition lives in assemble_payload.py to keep
# it co-located with the logic that decides when to apply it.
#
# Usage:
#   from nlp_formation import STRUCTURAL_DISCOVERY_VUS_DIRECTIVE
#   system_prompt = STRUCTURAL_DISCOVERY_VUS_DIRECTIVE
#
# Injected automatically into payloads whose status == "STRUCTURAL_DISCOVERY_VUS".
try:
    from assemble_payload import STRUCTURAL_DISCOVERY_VUS_DIRECTIVE  # noqa: F401
except ImportError:
    # Fallback if assemble_payload is unavailable at import time
    STRUCTURAL_DISCOVERY_VUS_DIRECTIVE = (
        "SYSTEM DIRECTIVE — STRUCTURAL_DISCOVERY_VUS: "
        "Prioritize deterministic structural perturbations (ΔV, ΔSASA, backbone strain) "
        "as ground truth. Treat absent clinical literature as a discovery gap, not a "
        "computational failure. Provide a Predictive Pathogenicity verdict."
    )


def load_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        raise NLPFormationError(f"Failed to load JSON from {path}: {e}")

def extract_signals(physics):
    """
    Extracts structured metrics safely from JSON dicts.
    Also captures qualitative mechanism_tags injected by orchestration.
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

    # Qualitative mechanism tags injected by orchestration (e.g., from analyze_structure)
    mechanism_tags = physics.get("mechanism_tags", [])

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
        "mechanism_tags": mechanism_tags,
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
    elif exposure == "Exposed" and dH > 3.0:   # raised from 1.0 → matches severity gate
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

def _build_mechanistic_keywords(signals):
    """
    Maps raw delta values to biological keyword phrases for RAG compatibility.
    Returns a list of (keyword, category) tuples.

    Thresholds are intentionally conservative and aligned with the severity
    gates in assemble_payload.evaluate_physics_severity so that a benign
    conservative substitution (e.g. M129V) produces an empty list rather
    than spurious pathogenic vocabulary.
    """
    keywords = []
    dV = signals["delta_vol"]
    dH = signals["delta_hydro"]
    dC = signals["delta_charge"]
    exposure = signals["exposure"]
    sec_struct = signals["sec_struct"]
    plddt = signals["plddt"]
    is_buried = (exposure == "Buried") or (signals.get("sasa", 100) < 15.0)

    # --- Volume: context-aware thresholds ---
    # Buried: >30 Å3 expansion OR <-30 Å3 cavity → structurally significant
    # Exposed: >60 Å3 expansion OR <-40 Å3 cavity → significant surface distortion
    if is_buried:
        if dV > 30:
            keywords.append(("steric hindrance", "volume"))
            keywords.append(("pocket expansion", "volume"))
        elif dV > 10:
            keywords.append(("steric crowding", "volume"))
        elif dV < -30:
            keywords.append(("cavity formation", "volume"))
            keywords.append(("protein destabilization", "volume"))
    else:  # exposed
        if dV > 60:
            keywords.append(("steric hindrance", "volume"))
            keywords.append(("pocket expansion", "volume"))
        elif dV > 25:
            keywords.append(("surface structural alteration", "volume"))
        elif dV < -40:   # raised from -20: conservative substitutions like M129V (dV=-22.9) stay silent
            keywords.append(("cavity formation", "volume"))
            keywords.append(("protein destabilization", "volume"))

    # --- Hydrophobicity ---
    # Thresholds aligned with assemble_payload.SEVERE_DELTA_HYDRO_* constants:
    #   surface gain threshold: >3.0  (not >1.0 — avoids flagging M129V at +2.3)
    #   buried loss threshold:  <-2.5
    if is_buried and dH < -2.5:
        keywords.append(("polar shift", "hydrophobicity"))
        keywords.append(("hydrophilic substitution", "hydrophobicity"))
    elif not is_buried and dH < -1.5:
        keywords.append(("reduced surface hydrophobicity", "hydrophobicity"))
    if not is_buried and dH > 3.0:   # raised from 1.0 → matches severity gate
        keywords.append(("aberrant surface hydrophobicity", "hydrophobicity"))
        keywords.append(("aggregation propensity", "hydrophobicity"))
        keywords.append(("amyloid formation", "hydrophobicity"))

    # --- Charge ---
    if dC != 0 and not is_buried:
        keywords.append(("electrostatic perturbation", "charge"))
    elif dC != 0 and is_buried:
        keywords.append(("buried charge disruption", "charge"))
        keywords.append(("protein unfolding", "charge"))

    # --- Secondary structure context ---
    # Only appended when at least one delta keyword fired, so structure context
    # doesn't appear alone for a completely benign substitution.
    if keywords:
        sec_lower = sec_struct.lower()
        if "alpha" in sec_lower or "helix" in sec_lower:
            keywords.append(("alpha-helix disruption", "structure"))
            keywords.append(("helical stability", "structure"))
        elif "beta" in sec_lower or "sheet" in sec_lower:
            keywords.append(("beta-sheet remodelling", "structure"))
        elif "loop" in sec_lower:
            keywords.append(("loop flexibility", "structure"))

    # --- pLDDT disorder ---
    if plddt < 50:
        keywords.append(("intrinsically disordered region", "disorder"))
        keywords.append(("conformational flexibility", "disorder"))
    elif plddt < 70:
        keywords.append(("structurally dynamic region", "disorder"))

    # Qualitative tags injected by orchestration
    for tag in signals.get("mechanism_tags", []):
        keywords.append((tag, "qualitative"))

    return keywords


def _build_variant_aliases(signals):
    """
    Produces the set of variant string aliases used as keyword boost hints.
    E.g. A53T → ['A53T', 'Ala53Thr', 'alanine 53 threonine'].
    """
    wt = signals["wt"].capitalize()   # e.g. Ala
    mut = signals["mut"].capitalize() # e.g. Thr
    pos = signals["pos"]              # e.g. 53
    raw = signals["variant"]          # e.g. A53T

    aliases = [
        raw,                          # A53T
        f"{wt}{pos}{mut}",            # Ala53Thr
    ]
    return list(dict.fromkeys(aliases))  # deduplicated


def construct_query(signals, mechanisms):
    """
    Hybrid Query Builder: RAG-optimized query that combines
      1. Explicit mutation signature (gene+variant anchor)
      2. Mechanistic narrative built from biological keywords, not raw math
      3. Structural context from the secondary structure field
      4. RAG expansion vocabulary for literature matching

    Returns a tuple: (query_string, keyword_boost_hints)
    where keyword_boost_hints contains exact variant aliases for the safety-net reranker.
    """
    variant_aliases = _build_variant_aliases(signals)
    bio_keywords = _build_mechanistic_keywords(signals)

    # ── Part 1: Mutation Signature (explicit gene+variant anchor) ─────────────
    # Prefer the raw variant code (e.g. A53T) as the anchor; gene is added by
    # the caller (run_nlp_formation) if available.
    signature = f"{signals['variant']} ({{signals['wt']}}→{{signals['mut']}} at position {signals['pos']})"
    signature = f"{signals['variant']} ({signals['wt']}→{signals['mut']} at position {signals['pos']})"

    # ── Part 2: Mechanistic Narrative (delta-to-keyword mapping) ─────────────
    # Prefer bio_keywords; fall back to interpreted mechanisms from interpret_and_prioritize
    kw_phrases = [kw for kw, _ in bio_keywords]
    if kw_phrases:
        kw_deduped = list(dict.fromkeys(kw_phrases))[:5]  # top 5, no duplicates
        if len(kw_deduped) > 1:
            kw_str = ", ".join(kw_deduped[:-1]) + ", and " + kw_deduped[-1]
        else:
            kw_str = kw_deduped[0]
        narrative = f"This substitution is associated with {kw_str}"
    elif mechanisms:
        mech_clean = [re.sub(r"\(Δ[^)]+\)", "", m).strip() for m in mechanisms]
        narrative = f"This substitution is associated with {', '.join(mech_clean)}"
    else:
        narrative = f"This substitution has an ambiguous structural impact"

    # ── Part 3: Structural Context ────────────────────────────────────────────
    sec_struct = signals["sec_struct"]
    sec_lower = sec_struct.lower()
    if "alpha" in sec_lower or "helix" in sec_lower:
        struct_ctx = "occurring within an alpha-helix"
    elif "beta" in sec_lower or "sheet" in sec_lower:
        struct_ctx = "occurring within a beta-sheet"
    elif "loop" in sec_lower:
        struct_ctx = "occurring within a flexible loop"
    else:
        struct_ctx = f"occurring in a {sec_struct} region"

    # ── Part 4: Disease/Pathway RAG Expansion ─────────────────────────────────
    # Only fire expansion keywords when a delta keyword actually crossed a
    # severity threshold.  Track which categories fired rather than doing a
    # string-match on the assembled keyword list (which caused M129V to
    # inherit "amyloid formation" vocabulary via the keyword text itself).
    kw_categories = {cat for _, cat in bio_keywords}
    mech_text = " ".join(kw_phrases).lower() + " " + " ".join(mechanisms).lower()
    expansion_kws = []

    has_aggregation_signal = (
        "hydrophobicity" in kw_categories
        and any(t in mech_text for t in ["aggregation", "amyloid", "fibrillation", "aberrant"])
    )
    has_steric_signal = (
        "volume" in kw_categories
        and any(t in mech_text for t in ["steric", "cavity", "pocket", "destabiliz"])
    )
    has_disorder_signal = (
        "disorder" in kw_categories
        or ("structure" in kw_categories
            and any(t in mech_text for t in ["disordered", "dynamic", "flexible", "helix"]))
    )

    if has_aggregation_signal:
        expansion_kws.extend(["misfolding", "amyloidogenesis", "fibrillation", "Parkinson's disease"])
    if has_steric_signal:
        expansion_kws.extend(["conformational change", "protein stability", "structural perturbation"])
    if has_disorder_signal:
        expansion_kws.extend(["intrinsically disordered protein", "conformational ensemble"])

    # If NO violations fired at all, use neutral variant-study expansion so the
    # query still retrieves relevant population/susceptibility papers.
    if not bio_keywords and not mechanisms:
        expansion_kws = ["polymorphism", "susceptibility", "population genetics", "common variant"]


    # ── Assemble Final Query ──────────────────────────────────────────────────
    expansion_deduped = list(dict.fromkeys(expansion_kws))[:4]
    query_parts = [
        f"Mutation {signature}, {struct_ctx}.",
        f"{narrative}.",
    ]
    if expansion_deduped:
        exp_str = ", ".join(expansion_deduped)
        query_parts.append(f"Relevant literature includes studies on: {exp_str}.")


    query_string = " ".join(query_parts)
    return query_string, variant_aliases

def create_nlp_query(physics):
    """
    Entry point for dictionary-based physics input.
    Returns a tuple: (query_string, keyword_boost_hints).
    """
    signals = extract_signals(physics)
    mechanisms = interpret_and_prioritize(signals)
    return construct_query(signals, mechanisms)

def create_nlp_query_from_file(physics_path):
    """
    Loads physics JSON and generates query.
    Returns a tuple: (query_string, keyword_boost_hints).
    """
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
        Tuple (query_string, keyword_boost_hints) where:
          - query_string: the biological narrative query for RAG retrieval
          - keyword_boost_hints: list of exact variant alias strings (e.g. ['A53T', 'Ala53Thr'])
            that vector_engine uses for its keyword safety-net score boost.
    """
    base = f"{gene}_{variant}"
    physics_path = os.path.join(data_dir, "analysis", f"{base}_physics.json")
    output_dir = os.path.join(data_dir, "NLP queries")
    output_path = os.path.join(output_dir, f"{base}_query.txt")

    logger.info(f"Generating NLP query for {gene} {variant}...")
    query_string, keyword_boost_hints = create_nlp_query_from_file(physics_path)

    # Prepend the gene symbol to give an explicit mutation signature anchor
    if not query_string.startswith(gene):
        query_string = f"{gene} {query_string}"

    os.makedirs(output_dir, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(query_string)

    logger.info(f"NLP query saved to {output_path}")
    return query_string, keyword_boost_hints

def main():
    parser = argparse.ArgumentParser(description="Generate NLP query via semantic translation of Physics/Context signals.")
    parser.add_argument("gene", help="Gene symbol, e.g. SNCA")
    parser.add_argument("variant", help="Variant code, e.g. A53T")
    parser.add_argument("--data-dir", default="data", help="Base data directory")
    args = parser.parse_args()

    try:
        query_string, keyword_boost_hints = run_nlp_formation(args.gene, args.variant, args.data_dir)
        print(f"\nQuery:\n{query_string}")
        print(f"\nKeyword Boost Hints: {keyword_boost_hints}")
        return 0
    except Exception as e:
        logger.error(f"NLP Formation failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())

