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
        "as preliminary hypotheses, not ground truth. Treat absent clinical literature "
        "as a discovery gap, not a computational failure, and recommend experimental "
        "validation before any pathogenicity conclusion."
    )


AA_1_TO_3 = {
    "A": "Ala", "R": "Arg", "N": "Asn", "D": "Asp", "C": "Cys",
    "Q": "Gln", "E": "Glu", "G": "Gly", "H": "His", "I": "Ile",
    "L": "Leu", "K": "Lys", "M": "Met", "F": "Phe", "P": "Pro",
    "S": "Ser", "T": "Thr", "W": "Trp", "Y": "Tyr", "V": "Val",
}
AA_3_TO_1 = {v.upper(): k for k, v in AA_1_TO_3.items()}

# Generic/uninformative condition strings returned by ClinVar/Ensembl that add
# noise to dense retrieval queries.
_NOISY_DISEASE_TERMS = {
    "not provided",
    "not specified",
    "clinvar: phenotype not specified",
    "annotated by hgmd",
    "inborn genetic diseases",
    "hereditary disease",
    "genetic disease",
    "phenotype not specified",
    "see cases",
}


def load_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        raise NLPFormationError(f"Failed to load JSON from {path}: {e}")


def _safe_float(val, default=0.0):
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val, default=0):
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _to_three_letter(residue):
    if not residue:
        return ""
    clean = str(residue).strip()
    upper = clean.upper()
    if upper in AA_1_TO_3:
        return AA_1_TO_3[upper]
    if upper in AA_3_TO_1:
        return upper.capitalize()
    return clean.capitalize()


def extract_signals(physics):
    """
    Extracts structured Biopython structural metrics and ThermoMPNN scores
    safely from a physics/structural-heuristics JSON dict.
    Also captures qualitative mechanism_tags injected by orchestration.
    """
    physics = physics or {}
    variant = str(physics.get("variant", "") or "").strip()

    m = re.match(r"([A-Za-z]+)(\d+)([A-Za-z*]+)", variant)
    if m:
        wt, pos, mut = m.groups()
    else:
        if variant:
            logger.warning(f"Could not parse variant string: {variant}. Using placeholders.")
        wt, pos, mut = "?", "?", "?"

    comp_view = physics.get("comparison_view") or {}
    res_view = comp_view.get("residue") or {}
    wt_residue = res_view.get("wt") or wt
    mut_residue = res_view.get("mut") or mut

    deltas = physics.get("deltas") or {}
    delta_vol = _safe_float(deltas.get("delta_volume"))
    delta_hydro = _safe_float(deltas.get("delta_hydrophobicity"))
    delta_charge = _safe_float(deltas.get("delta_charge"))

    wt_context = physics.get("structural_context_wt") or {}
    exposure = str(wt_context.get("exposure") or "Unknown")
    sasa = _safe_float(wt_context.get("sasa"))
    sec_struct = str(wt_context.get("secondary_structure") or "Unknown")
    plddt = _safe_float(wt_context.get("plddt_confidence"), 100.0)

    stability_audit = physics.get("stability_audit") or {}
    h_bonds_lost = _safe_int(stability_audit.get("h_bonds_lost_est"), 0)
    salt_bridges_lost = stability_audit.get("salt_bridges_lost") or []
    if not isinstance(salt_bridges_lost, list):
        salt_bridges_lost = []
    disulfides_lost = stability_audit.get("disulfides_lost") or []
    if not isinstance(disulfides_lost, list):
        disulfides_lost = []
    backbone_strain = str(stability_audit.get("backbone_strain") or "None").strip()

    interface_contacts_lost = _safe_int(physics.get("interface_contacts_lost"), 0)

    raw_agg = physics.get("delta_aggregation")
    delta_aggregation = None if raw_agg is None else _safe_float(raw_agg)

    mechanism_tags = physics.get("mechanism_tags") or []
    if not isinstance(mechanism_tags, list):
        mechanism_tags = []

    raw_ddg = physics.get("monomer_ddg")
    monomer_ddg = None if raw_ddg is None else _safe_float(raw_ddg)

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
        "h_bonds_lost": h_bonds_lost,
        "salt_bridges_lost": salt_bridges_lost,
        "disulfides_lost": disulfides_lost,
        "backbone_strain": backbone_strain,
        "interface_contacts_lost": interface_contacts_lost,
        "delta_aggregation": delta_aggregation,
        "mechanism_tags": mechanism_tags,
        "monomer_ddg": monomer_ddg,
    }


def extract_clinical_signals(clinical_context, gene=None):
    """
    Extracts retrieval-useful, non-leaking clinical context signals:
      - rsid (from dbSNP) for exact-match boosting & query anchoring
      - hgvs_protein (e.g. 'p.Ala53Thr' from ClinGen Allele Registry)
      - diseases (deduplicated, cleaned top disease/phenotype names from
        ClinVar conditions, OpenTargets precision layer, and Ensembl recall layer)

    Deliberately excludes pathogenicity verdicts (e.g. ClinVar significance or
    AlphaMissense labels) so retrieval stays unbiased.
    """
    if not isinstance(clinical_context, dict):
        return {"rsid": None, "hgvs_protein": None, "diseases": []}

    # 1. dbSNP rsID
    rsid = None
    dbsnp = clinical_context.get("dbsnp")
    if isinstance(dbsnp, dict) and dbsnp.get("rsid"):
        rsid = str(dbsnp["rsid"]).strip()

    # 2. HGVS protein notation from ClinGen Allele Registry (e.g. "p.Ala53Thr")
    hgvs_protein = None
    clingen = clinical_context.get("clingenreg")
    if isinstance(clingen, dict):
        hgvs_used = str(clingen.get("hgvs_used") or "")
        m = re.search(r"(p\.[A-Za-z]{3}\d+[A-Za-z*]{1,3})", hgvs_used)
        if m:
            hgvs_protein = m.group(1)

    # 3. Disease / phenotype names (ordered by specificity)
    raw_diseases = []

    # 3a. ClinVar exact-variant conditions
    clinvar = clinical_context.get("clinvar")
    if isinstance(clinvar, dict):
        conditions = clinvar.get("conditions")
        if isinstance(conditions, list):
            raw_diseases.extend(conditions)

    # 3b. OpenTargets validated gene-disease associations
    gene_ctx = clinical_context.get("gene_level_context") or {}
    ot = gene_ctx.get("precision_layer_opentargets") or {}
    if isinstance(ot, dict):
        for entry in ot.get("top_diseases") or []:
            if isinstance(entry, dict) and entry.get("disease"):
                raw_diseases.append(entry["disease"])

    # 3c. Ensembl recall layer fallback
    ensembl = gene_ctx.get("recall_layer_ensembl") or {}
    if isinstance(ensembl, dict):
        for entry in ensembl.get("top_diseases") or []:
            if isinstance(entry, dict) and entry.get("disease"):
                raw_diseases.append(entry["disease"])

    gene_lower = (gene or clinical_context.get("gene") or "").strip().lower()
    seen = set()
    diseases = []
    for item in raw_diseases:
        if not item:
            continue
        term = re.sub(r"\s+", " ", str(item)).strip()
        lower = term.lower()
        if not term or lower in _NOISY_DISEASE_TERMS:
            continue
        if gene_lower and lower == f"{gene_lower}-related disorder":
            continue
        # Normalize punctuation/apostrophes for dedup (e.g. "Parkinson's disease" vs "Parkinson disease")
        norm = re.sub(r"[^a-z0-9]+", " ", lower.replace("'s", "")).strip()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        diseases.append(term)
        if len(diseases) >= 3:
            break

    return {
        "rsid": rsid,
        "hgvs_protein": hgvs_protein,
        "diseases": diseases,
    }


def interpret_and_prioritize(signals):
    """
    Mechanisms grounded in 3D Biopython structural measurements or ThermoMPNN.

    Residue-table deltas (Δvolume, Δhydrophobicity, Δcharge) are NOT mechanisms.
    Low pLDDT describes the wild-type model. ThermoMPNN is included only at or
    above +1.0 kcal/mol.
    """
    mechanisms = []

    monomer_ddg = signals.get("monomer_ddg")
    if monomer_ddg is not None and monomer_ddg >= 1.0:
        mechanisms.append((10, f"predicted monomer destabilization (ThermoMPNN ΔΔG={monomer_ddg:+.2f} kcal/mol)"))

    disulfides = signals.get("disulfides_lost") or []
    if disulfides:
        mechanisms.append((9, f"disulfide bond disruption ({', '.join(disulfides)})"))

    salt_bridges = signals.get("salt_bridges_lost") or []
    if salt_bridges:
        mechanisms.append((8, f"salt bridge disruption ({', '.join(salt_bridges)})"))

    backbone_strain = (signals.get("backbone_strain") or "None").strip()
    if backbone_strain and backbone_strain.lower() != "none":
        mechanisms.append((8, f"backbone conformational strain ({backbone_strain})"))

    interface_lost = signals.get("interface_contacts_lost", 0)
    if interface_lost >= 1:
        mechanisms.append((7, f"protein-protein interface contact loss ({interface_lost} contacts)"))

    plddt = signals["plddt"]
    if plddt < 50:
        mechanisms.append((7, f"wild-type model confidence is low at this site (pLDDT={plddt:.1f})"))
    elif plddt < 70:
        mechanisms.append((5, f"wild-type model confidence is moderate at this site (pLDDT={plddt:.1f})"))

    h_bonds_lost = signals.get("h_bonds_lost", 0)
    if h_bonds_lost >= 2:
        mechanisms.append((6, f"hydrogen bond network loss ({h_bonds_lost} estimated polar contacts)"))

    delta_agg = signals.get("delta_aggregation")
    if delta_agg is not None and delta_agg >= 0.05:
        mechanisms.append((6, f"increased sequence aggregation propensity (Δa4v={delta_agg:+.3f})"))

    mechanisms.sort(key=lambda x: x[0], reverse=True)
    return [m[1] for m in mechanisms[:3]]


def _build_mechanistic_keywords(signals):
    """
    Literature keywords come from Biopython 3D structural measurements
    (disulfides, salt bridges, backbone strain, interface contacts, H-bonds,
    wild-type pLDDT, AGGRESCAN delta_aggregation) and ThermoMPNN monomer ΔΔG.
    Residue-table deltas (Δvolume, Δhydrophobicity, Δcharge) do NOT add
    pathogenic phrases.
    """
    keywords = []

    # ThermoMPNN monomer ΔΔG, positive = destabilizing. Below 1 kcal/mol stays silent.
    monomer_ddg = signals.get("monomer_ddg")
    if monomer_ddg is not None and monomer_ddg >= 1.0:
        keywords.append(("monomer destabilization", "stability"))

    # Biopython 3D structural interactions
    if signals.get("disulfides_lost"):
        keywords.append(("disulfide bond disruption", "stability"))
    if signals.get("salt_bridges_lost"):
        keywords.append(("salt bridge disruption", "electrostatics"))

    backbone_strain = (signals.get("backbone_strain") or "None").strip().lower()
    if "proline" in backbone_strain:
        keywords.append(("proline helix disruption", "backbone"))
    elif "glycine" in backbone_strain:
        keywords.append(("glycine backbone conformational strain", "backbone"))
    elif backbone_strain and backbone_strain != "none":
        keywords.append((backbone_strain, "backbone"))

    if signals.get("interface_contacts_lost", 0) >= 1:
        keywords.append(("protein-protein interface disruption", "interface"))

    if signals.get("h_bonds_lost", 0) >= 2:
        keywords.append(("hydrogen bond loss", "stability"))

    delta_agg = signals.get("delta_aggregation")
    if delta_agg is not None and delta_agg >= 0.05:
        keywords.append(("aggregation propensity", "aggregation"))

    # Wild-type AlphaFold pLDDT disorder
    plddt = signals["plddt"]
    if plddt < 50:
        keywords.append(("intrinsically disordered region", "disorder"))
        keywords.append(("conformational flexibility", "disorder"))
    elif plddt < 70:
        keywords.append(("structurally dynamic region", "disorder"))

    # Qualitative tags injected by orchestration
    for tag in signals.get("mechanism_tags", []):
        if tag:
            keywords.append((str(tag), "qualitative"))

    return keywords


def _build_variant_aliases(signals, clinical_signals=None):
    """
    Produces the set of exact variant identifier aliases used as keyword boost
    hints by vector_engine's cross-encoder safety net.
    E.g. A53T + rs104893877 → ['A53T', 'Ala53Thr', 'p.Ala53Thr', 'rs104893877'].
    """
    raw = signals["variant"]
    pos = signals["pos"]
    wt_3 = _to_three_letter(signals["wt"])
    mut_3 = _to_three_letter(signals["mut"])

    aliases = []
    if raw:
        aliases.append(raw)
    if wt_3 and mut_3 and pos and pos != "?":
        three_letter = f"{wt_3}{pos}{mut_3}"
        aliases.append(three_letter)
        aliases.append(f"p.{three_letter}")

    if isinstance(clinical_signals, dict):
        if clinical_signals.get("hgvs_protein"):
            aliases.append(clinical_signals["hgvs_protein"])
        if clinical_signals.get("rsid"):
            aliases.append(clinical_signals["rsid"])

    return list(dict.fromkeys(a for a in aliases if a))


def _format_structural_site(signals):
    """Formats Biopython DSSP secondary structure + Shrake-Rupley exposure concisely."""
    sec_struct = (signals.get("sec_struct") or "Unknown").strip()
    sec_lower = sec_struct.lower()
    exposure = (signals.get("exposure") or "Unknown").strip().lower()
    plddt = signals.get("plddt", 100.0)

    if "alpha" in sec_lower or "helix" in sec_lower:
        sec_phrase = "alpha-helix"
    elif "beta" in sec_lower or "sheet" in sec_lower or "bridge" in sec_lower:
        sec_phrase = "beta-sheet"
    elif "turn" in sec_lower or "bend" in sec_lower:
        sec_phrase = "turn region"
    elif "loop" in sec_lower:
        sec_phrase = "low-confidence loop" if plddt < 70 else "loop region"
    elif sec_lower and sec_lower != "unknown":
        sec_phrase = f"{sec_lower} region"
    else:
        sec_phrase = ""

    exp_phrase = ""
    if exposure in {"buried", "partially exposed", "exposed"}:
        exp_phrase = exposure

    if exp_phrase and sec_phrase:
        return f"{exp_phrase} {sec_phrase}"
    if sec_phrase:
        return sec_phrase
    if exp_phrase:
        return f"{exp_phrase} site"
    return ""


def construct_query(signals, mechanisms, clinical_context=None, gene=None):
    """
    Hybrid Query Builder optimized for biomedical dense retrieval
    (S-PubMedBert-MS-MARCO + MS-MARCO cross-encoder).

    Combines:
      1. Explicit gene + variant signature anchor (1-letter, 3-letter, rsID)
      2. Biopython 3D structural site (exposure + DSSP secondary structure)
      3. Grounded mechanistic keywords (Biopython 3D interactions, ThermoMPNN, pLDDT)
      4. Clinical disease/phenotype context (ClinVar / OpenTargets / Ensembl)

    Returns a tuple: (query_string, keyword_boost_hints)
    """
    clinical_signals = extract_clinical_signals(clinical_context, gene=gene)
    variant_aliases = _build_variant_aliases(signals, clinical_signals)
    bio_keywords = _build_mechanistic_keywords(signals)

    # ── Part 1: Gene + Variant Signature Anchor ───────────────────────────────
    wt_3 = _to_three_letter(signals["wt"])
    mut_3 = _to_three_letter(signals["mut"])
    pos = signals["pos"]
    three_letter = f"{wt_3}{pos}{mut_3}" if (wt_3 and mut_3 and pos and pos != "?") else ""

    anchor_extras = []
    if three_letter and three_letter != signals["variant"]:
        anchor_extras.append(three_letter)
    if clinical_signals["rsid"]:
        anchor_extras.append(clinical_signals["rsid"])

    gene_prefix = f"{gene.strip()} " if gene and str(gene).strip() else ""
    if anchor_extras:
        signature = f"{gene_prefix}{signals['variant']} ({', '.join(anchor_extras)}) missense variant"
    else:
        signature = f"{gene_prefix}{signals['variant']} missense variant"

    # ── Part 2: Biopython Structural Site ─────────────────────────────────────
    struct_site = _format_structural_site(signals)
    lead = f"{signature} in {struct_site}" if struct_site else signature

    clauses = [lead]

    # ── Part 3: Grounded Mechanistic Terms ────────────────────────────────────
    kw_phrases = list(dict.fromkeys(kw for kw, _ in bio_keywords))[:5]
    if kw_phrases:
        clauses.append(", ".join(kw_phrases))

    # ── Part 4: Clinical / Disease Context ────────────────────────────────────
    diseases = clinical_signals["diseases"]
    if diseases:
        clauses.append(f"associated with {', '.join(diseases)}")

    # Neutral fallback when neither structural mechanisms nor diseases are known
    if not kw_phrases and not diseases:
        clauses.append("functional impact and protein structure")

    query_string = "; ".join(clauses) + "."
    return query_string, variant_aliases


def create_nlp_query(physics, clinical_context=None, gene=None):
    """
    Entry point for dictionary-based physics + optional clinical context input.
    Returns a tuple: (query_string, keyword_boost_hints).
    """
    signals = extract_signals(physics)
    mechanisms = interpret_and_prioritize(signals)
    return construct_query(signals, mechanisms, clinical_context=clinical_context, gene=gene)


def create_nlp_query_from_file(physics_path, clinical_context=None, gene=None):
    """
    Loads physics JSON and generates query.
    Returns a tuple: (query_string, keyword_boost_hints).
    """
    if not os.path.exists(physics_path):
        raise NLPFormationError(f"Missing physics file: {physics_path}")
    physics = load_json(physics_path)
    return create_nlp_query(physics, clinical_context=clinical_context, gene=gene)


def _resolve_physics_path(gene, variant, data_dir="data", physics_path=None):
    if physics_path and os.path.exists(physics_path):
        return physics_path
    base = f"{gene}_{variant}"
    candidates = [
        os.path.join(data_dir, "analysis", f"{base}_physics.json"),
        os.path.join(data_dir, "structure", f"{base}_physics.json"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]


def run_nlp_formation(
    gene,
    variant,
    data_dir="data",
    clinical_context=None,
    physics_path=None,
    mechanism_tags=None,
):
    """
    Exportable function to generate an NLP query for a specific gene/variant.

    Args:
        gene: Gene symbol
        variant: Variant code
        data_dir: Base directory for data
        clinical_context: Optional clinical context dict; if None, loads
            ``{data_dir}/context/{gene}_{variant}_context.json`` when present.
        physics_path: Optional explicit path to physics JSON; otherwise checks
            ``{data_dir}/analysis/`` then ``{data_dir}/structure/``.
        mechanism_tags: Optional qualitative mechanism tags to include.

    Returns:
        Tuple (query_string, keyword_boost_hints) where:
          - query_string: concise biomedical query for RAG retrieval
          - keyword_boost_hints: list of exact variant alias strings
            (e.g. ['A53T', 'Ala53Thr', 'p.Ala53Thr', 'rs104893877'])
            that vector_engine uses for its keyword safety-net score boost.
    """
    base = f"{gene}_{variant}"
    resolved_physics_path = _resolve_physics_path(
        gene, variant, data_dir=data_dir, physics_path=physics_path
    )
    output_dir = os.path.join(data_dir, "NLP queries")
    output_path = os.path.join(output_dir, f"{base}_query.txt")

    if clinical_context is None:
        ctx_path = os.path.join(data_dir, "context", f"{base}_context.json")
        if os.path.exists(ctx_path):
            try:
                clinical_context = load_json(ctx_path)
            except NLPFormationError as exc:
                logger.warning(f"Could not load clinical context from {ctx_path}: {exc}")

    logger.info(f"Generating NLP query for {gene} {variant}...")
    if not os.path.exists(resolved_physics_path):
        raise NLPFormationError(f"Missing physics file: {resolved_physics_path}")

    physics = load_json(resolved_physics_path)
    if mechanism_tags:
        physics["mechanism_tags"] = list(mechanism_tags)

    query_string, keyword_boost_hints = create_nlp_query(
        physics, clinical_context=clinical_context, gene=gene
    )

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
