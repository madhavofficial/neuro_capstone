"""
Assemble Payload Module

Processes ranked evidence chunks from vector_engine and constructs
a structured, machine-readable JSON payload for downstream LLM consumption.

Key responsibilities:
- Threshold filtering (confidence gate)
- Deduplication (max 1-2 chunks per PMID)
- Deterministic sorting (by score, descending)
- Modular confidence_matrix construction (per-engine granular status)
- Global status derivation via the confidence matrix logic gate
- Structured JSON output with LLM system-prompt directive when applicable

───────────────────────────────────────────────────
  CONFIDENCE MATRIX SCHEMA
───────────────────────────────────────────────────
  confidence_matrix: {
    physics_engine:    "HEURISTIC" | "ERROR"
    literature_rag:    "SUCCESS" | "NULL_RESULTS" | "TIMEOUT_ERROR"
    clinical_context:  "HIGH" | "PARTIAL" | "UNAVAILABLE"
  }

───────────────────────────────────────────────────
  GLOBAL STATUS VALUES
───────────────────────────────────────────────────
  SUCCESS                  ≥1 RAG hit above threshold
  LOW_CONFIDENCE           some RAG hits, none above threshold
  STRUCTURAL_DISCOVERY_VUS physics HEURISTIC + clinical HIGH/PARTIAL
                           + RAG NULL_RESULTS or TIMEOUT_ERROR
                           (strong structural math, zero literature)
  PREDICTED_PATHOGENIC_VUS zero evidence + severe physics violation
                           (legacy code-path, kept for compatibility)
"""

import json
import os
from typing import List, Dict, Any, Optional, Tuple


# ── General configuration ──────────────────────────────────────────────────────
CONFIDENCE_THRESHOLD   = 0.7
MAX_CHUNKS_PER_PMID    = 2
OUTPUT_PATH            = "data/context_payload.json"

# ── Confidence-matrix value constants ─────────────────────────────────────────
# physics_engine
CM_PHYSICS_HEURISTIC = "HEURISTIC"
CM_PHYSICS_ERROR   = "ERROR"

# literature_rag
CM_RAG_SUCCESS     = "SUCCESS"
CM_RAG_NULL        = "NULL_RESULTS"
CM_RAG_TIMEOUT     = "TIMEOUT_ERROR"

# clinical_context
CM_CLINICAL_HIGH   = "HIGH"
CM_CLINICAL_PARTIAL= "PARTIAL"
CM_CLINICAL_UNAVAIL= "UNAVAILABLE"

# ── Physics severity thresholds ───────────────────────────────────────────────
# Calibrated against the real physics JSON schema produced by analyze_structure.
SEVERE_DELTA_VOLUME_BURIED    = 30.0
SEVERE_DELTA_VOLUME_EXPOSED   = 60.0
SEVERE_DELTA_HYDRO_SURFACE_GAIN =  3.0
SEVERE_DELTA_HYDRO_BURIED_LOSS  = -2.5
SEVERE_BURIED_CHARGE_SHIFT      = True

SEVERE_BACKBONE_STRAIN_LABELS = {
    "glycine flexibility lost",
    "severe",
    "high",
    "critical",
}

SEVERE_VIOLATION_MIN_AXES = 1

# ── LLM system-prompt directive injected when status = STRUCTURAL_DISCOVERY_VUS ──
STRUCTURAL_DISCOVERY_VUS_DIRECTIVE = (
    "SYSTEM DIRECTIVE — STRUCTURAL_DISCOVERY_VUS: "
    "The variant below has no peer-reviewed clinical literature but carries a "
    "computational structural heuristic derived from an AlphaFold model and residue "
    "property deltas (ΔV, ΔSASA, backbone strain, hydrophobic shift). This is not a "
    "validated physical simulation or clinical classification. "
    "Treat the absence of clinical literature as a 'discovery gap' — an opportunity "
    "for novel scientific inquiry — NOT as evidence of benignity or a computational "
    "failure. Provide a 'Predictive Pathogenicity' verdict grounded in the structural "
    "math, explicitly acknowledging the literature gap and recommending experimental "
    "validation (e.g., ThT aggregation assay, CD spectroscopy, cellular toxicity model)."
)


# ──────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _safe_float(val, default: float = 0.0) -> float:
    """Safely coerce a JSON value to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


# ──────────────────────────────────────────────────────────────────────────────
#  Confidence matrix builder
# ──────────────────────────────────────────────────────────────────────────────

def build_confidence_matrix(
    physics_vector:   Optional[Dict[str, Any]],
    rag_status:       str,
    clinical_context: Optional[Dict[str, Any]],
) -> Dict[str, str]:
    """
    Construct the per-engine confidence_matrix object.

    Args:
        physics_vector:
            Dict loaded from ``*_physics.json``.  If None or empty the engine
            is marked ERROR (BioPython analysis did not complete).
        rag_status:
            One of CM_RAG_SUCCESS / CM_RAG_NULL / CM_RAG_TIMEOUT.  Callers
            are expected to derive this from their retrieval outcome.
        clinical_context:
            Dict loaded from ``*_context.json`` (fetch_context output).
            The matrix inspects for ClinVar or AlphaMissense keys to decide
            between HIGH / PARTIAL / UNAVAILABLE.

    Returns:
        Dict with keys: physics_engine, literature_rag, clinical_context
    """
    # ── physics_engine ────────────────────────────────────────────────────────
    physics_ok = bool(physics_vector and physics_vector.get("deltas"))
    # Current analysis compares amino-acid property tables against a WT
    # AlphaFold model; it does not generate or relax a mutant structure.
    # Therefore this is a heuristic signal, never a validated/high-confidence
    # physical simulation result.
    physics_val = CM_PHYSICS_HEURISTIC if physics_ok else CM_PHYSICS_ERROR

    # ── literature_rag ───────────────────────────────────────────────────────
    # Accept the caller-supplied value; validate it falls in the known set.
    known_rag = {CM_RAG_SUCCESS, CM_RAG_NULL, CM_RAG_TIMEOUT}
    rag_val = rag_status if rag_status in known_rag else CM_RAG_NULL

    # ── clinical_context ─────────────────────────────────────────────────────
    # HIGH   → ClinVar OR AlphaMissense data present AND has pathogenicity info
    # PARTIAL → one source present but incomplete
    # UNAVAILABLE → no clinical data
    clinical_val = CM_CLINICAL_UNAVAIL
    rich_sources = 0
    any_source = 0
    has_gene_level = False
    if clinical_context:
        clinvar         = clinical_context.get("clinvar") or {}
        has_exact_clinvar = bool(
            isinstance(clinvar, dict) and clinvar.get("variant_match") is True
        )
        has_clinvar     = has_exact_clinvar
        has_alphamiss   = bool(
            clinical_context.get("alphamissense")
            or clinical_context.get("alphamissense_sniper")
        )
        has_dbsnp       = bool(clinical_context.get("dbsnp"))
        has_clingen     = bool(
            clinical_context.get("clingen")
            or clinical_context.get("clingenreg")
        )

        rich_sources = sum([has_clinvar, has_alphamiss])
        any_source   = sum([has_clinvar, has_alphamiss, has_dbsnp, has_clingen])

        has_gene_level = bool(
            isinstance(clinvar, dict) and clinvar.get("scope") == "gene_level"
        )

        if rich_sources >= 1:
            clinical_val = CM_CLINICAL_HIGH
        elif any_source >= 1 or has_gene_level:
            clinical_val = CM_CLINICAL_PARTIAL

    return {
        "physics_engine":   physics_val,
        "literature_rag":   rag_val,
        "clinical_context": clinical_val,
        "clinical_context_scope": (
            "EXACT_VARIANT" if rich_sources >= 1 else
            "GENE_LEVEL" if (any_source >= 1 or has_gene_level) else
            "UNAVAILABLE"
        ),
        "physics_evidence_scope": (
            "SITE_PROPERTY_HEURISTIC" if physics_ok else "UNAVAILABLE"
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
#  Global status logic gate
# ──────────────────────────────────────────────────────────────────────────────

def derive_global_status(
    confidence_matrix: Dict[str, str],
    has_evidence:      bool,
    low_confidence:    bool,
    physics_vector:    Optional[Dict[str, Any]] = None,
) -> str:
    """
    Apply the confidence matrix logic gate to determine the global status string.

    Priority (highest → lowest):
      1. STRUCTURAL_DISCOVERY_VUS
           physics HEURISTIC  AND  clinical HIGH or PARTIAL
           AND  RAG is NULL_RESULTS or TIMEOUT_ERROR
      2. SUCCESS
           has_evidence AND NOT low_confidence
      3. LOW_CONFIDENCE
           has_evidence but none above threshold  (RAG retrieved but weak)
      4. PREDICTED_PATHOGENIC_VUS  (legacy path when physics is severe but
           evidence is absent and clinical_context is UNAVAILABLE)
      5. LOW_CONFIDENCE  (catch-all)

    Args:
        confidence_matrix: Output of build_confidence_matrix().
        has_evidence:      True if the evidence array is non-empty.
        low_confidence:    True if no evidence chunk cleared the score threshold.
        physics_vector:    Needed only for the PREDICTED_PATHOGENIC_VUS legacy check.

    Returns:
        Global status string.
    """
    pe  = confidence_matrix["physics_engine"]
    rag = confidence_matrix["literature_rag"]
    cc  = confidence_matrix["clinical_context"]

    # ── Rule 1: STRUCTURAL_DISCOVERY_VUS ──────────────────────────────────────
    rag_absent = rag in {CM_RAG_NULL, CM_RAG_TIMEOUT}
    clinical_good = cc in {CM_CLINICAL_HIGH, CM_CLINICAL_PARTIAL}

    if pe == CM_PHYSICS_HEURISTIC and rag_absent and clinical_good:
        return "STRUCTURAL_DISCOVERY_VUS"

    # ── Rule 2: SUCCESS ───────────────────────────────────────────────────────
    if has_evidence and not low_confidence:
        return "SUCCESS"

    # ── Rule 3: LOW_CONFIDENCE (RAG retrieved something but score too low) ────
    if has_evidence and low_confidence:
        return "LOW_CONFIDENCE"

    # ── Rule 4: PREDICTED_PATHOGENIC_VUS (legacy: no literature at all,
    #            no useful clinical data, but strong physics) ──────────────────
    if not has_evidence and physics_vector and cc == CM_CLINICAL_UNAVAIL:
        is_severe, _, _ = evaluate_physics_severity(physics_vector)
        if is_severe:
            return "PREDICTED_PATHOGENIC_VUS"

    # ── Rule 5: catch-all ─────────────────────────────────────────────────────
    return "LOW_CONFIDENCE"


# ──────────────────────────────────────────────────────────────────────────────
#  Physics severity evaluator
# ──────────────────────────────────────────────────────────────────────────────

def evaluate_physics_severity(
    physics_vector: Dict[str, Any],
) -> Tuple[bool, List[str], int]:
    """
    Evaluate whether the physics vector crosses a 'Severe' violation threshold.

    Evaluated axes (each contributes at most one violation):
      1. Volume change  (context-aware: buried vs exposed)
      2. Hydrophobicity change (surface gain or buried core loss)
      3. Backbone strain label
      4. Buried charge shift

    Returns:
        (is_severe, violations, violation_count)
    """
    violations: List[str] = []

    deltas    = physics_vector.get("deltas", {})
    ctx       = physics_vector.get("structural_context_wt", {})
    stability = physics_vector.get("stability_audit", {})

    dV       = _safe_float(deltas.get("delta_volume"))
    dH       = _safe_float(deltas.get("delta_hydrophobicity"))
    dC       = _safe_float(deltas.get("delta_charge"))
    exposure = ctx.get("exposure", "Unknown")
    sasa     = _safe_float(ctx.get("sasa"))
    backbone = str(stability.get("backbone_strain", "None")).lower()

    is_buried = (exposure == "Buried") or (sasa < 15.0)

    # Axis 1 — Volume
    threshold_vol = SEVERE_DELTA_VOLUME_BURIED if is_buried else SEVERE_DELTA_VOLUME_EXPOSED
    if abs(dV) > threshold_vol:
        direction = "expansion" if dV > 0 else "cavity"
        label = "±" if dV < 0 else ">"
        violations.append(
            f"Extreme volume {direction} (ΔV={dV:+.1f} Å³, "
            f"threshold={label}{threshold_vol:.0f} Å³ for "
            f"{'buried' if is_buried else 'exposed'} site)"
        )

    # Axis 2 — Hydrophobicity
    if not is_buried and dH > SEVERE_DELTA_HYDRO_SURFACE_GAIN:
        violations.append(
            f"Severe surface hydrophobicity gain (ΔH={dH:+.2f}, "
            f"threshold >+{SEVERE_DELTA_HYDRO_SURFACE_GAIN}) "
            "→ strong aggregation / amyloid propensity signal"
        )
    elif is_buried and dH < SEVERE_DELTA_HYDRO_BURIED_LOSS:
        violations.append(
            f"Severe hydrophobic core disruption (ΔH={dH:+.2f}, "
            f"threshold <{SEVERE_DELTA_HYDRO_BURIED_LOSS}) "
            "→ core packing collapse risk"
        )

    # Axis 3 — Backbone strain
    for label in SEVERE_BACKBONE_STRAIN_LABELS:
        if label in backbone and backbone != "none":
            violations.append(
                f"Severe backbone strain detected: "
                f"'{stability.get('backbone_strain')}' "
                "(loss of residue-specific φ/ψ conformational freedom)"
            )
            break

    # Axis 4 — Buried charge shift
    if SEVERE_BURIED_CHARGE_SHIFT and is_buried and dC != 0:
        violations.append(
            f"Buried charge shift (ΔCharge={dC:+.1f}) "
            "→ electrostatic destabilisation of hydrophobic core"
        )

    is_severe = len(violations) >= SEVERE_VIOLATION_MIN_AXES
    return is_severe, violations, len(violations)


# ──────────────────────────────────────────────────────────────────────────────
#  Note / directive builders
# ──────────────────────────────────────────────────────────────────────────────

def build_vus_note(
    physics_vector: Dict[str, Any],
    violations:     List[str],
    status:         str = "PREDICTED_PATHOGENIC_VUS",
) -> str:
    """
    Build the human-readable ``note`` field appended to VUS-class payloads.
    Works for both STRUCTURAL_DISCOVERY_VUS and PREDICTED_PATHOGENIC_VUS.
    """
    variant = physics_vector.get("variant", "Unknown variant")
    comp    = physics_vector.get("comparison_view", {})
    wt_res  = comp.get("residue", {}).get("wt", "?")
    mut_res = comp.get("residue", {}).get("mut", "?")
    ctx     = physics_vector.get("structural_context_wt", {})
    sec     = ctx.get("secondary_structure", "unknown region")
    plddt   = _safe_float(ctx.get("plddt_confidence"), 100.0)

    if plddt < 50:
        plddt_note = (
            f" The AlphaFold confidence score for this site is low (pLDDT={plddt:.1f}), "
            "indicating the residue sits within an intrinsically disordered region "
            "where mutations are often functionally consequential."
        )
    elif plddt < 70:
        plddt_note = (
            f" The site has moderate AlphaFold confidence (pLDDT={plddt:.1f}), "
            "consistent with a structurally dynamic region."
        )
    else:
        plddt_note = ""

    bullet_str = ("\n  • " + "\n  • ".join(violations)) if violations else ""

    if status == "STRUCTURAL_DISCOVERY_VUS":
        intro = (
            f"Variant {variant} ({wt_res}→{mut_res}) has no retrievable peer-reviewed "
            f"literature in indexed databases (Europe PMC / PubMed), but ClinVar / "
            f"AlphaMissense clinical data was successfully cross-referenced. "
        )
        classification = (
            "The deterministic structural model classifies this as a "
            "STRUCTURAL_DISCOVERY_VUS — a variant with a strong predicted "
            "pathogenic structural signal that currently lacks peer-reviewed literature "
            "confirmation (a discovery gap, not a computational failure)."
        )
    else:
        intro = (
            f"No peer-reviewed literature or clinical database records were retrieved "
            f"for {variant} ({wt_res}→{mut_res}). "
        )
        classification = (
            "This evidence-free structural signal warrants classification as a "
            "Variant of Uncertain Significance with Predicted Pathogenic Impact "
            "(PREDICTED_PATHOGENIC_VUS)."
        )

    note = (
        f"{intro}"
        f"The computational structural analysis identifies {len(violations)} severe "
        f"biophysical violation(s) at a {sec} site:{bullet_str}. "
        f"{classification}{plddt_note} "
        f"Independent experimental validation (e.g., ThT aggregation assay, "
        f"CD spectroscopy, or cellular toxicity study) is strongly recommended "
        f"before clinical interpretation."
    )
    return note


# ──────────────────────────────────────────────────────────────────────────────
#  RAG filtering helpers (unchanged)
# ──────────────────────────────────────────────────────────────────────────────

def filter_by_threshold(
    results:   List[Dict[str, Any]],
    threshold: float = CONFIDENCE_THRESHOLD,
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Apply confidence threshold filtering.

    Returns:
        (filtered_results, low_confidence_flag)
    """
    if not results:
        return [], True

    passed = [r for r in results if r.get("rerank_score", 0) >= threshold]
    if passed:
        return passed, False

    return [results[0]], True   # best fallback, flagged low confidence


def deduplicate_by_pmid(
    results:     List[Dict[str, Any]],
    max_per_pmid: int = MAX_CHUNKS_PER_PMID,
) -> List[Dict[str, Any]]:
    """Limit chunks per PMID to ensure evidence diversity."""
    counts: Dict[str, int] = {}
    out: List[Dict[str, Any]] = []
    for r in results:
        pmid = r.get("pmid")
        counts.setdefault(pmid, 0)
        if counts[pmid] < max_per_pmid:
            out.append(r)
            counts[pmid] += 1
    return out


def sort_by_score(
    results:    List[Dict[str, Any]],
    descending: bool = True,
) -> List[Dict[str, Any]]:
    """Sort deterministically by rerank_score."""
    return sorted(results, key=lambda x: x.get("rerank_score", 0), reverse=descending)


def construct_evidence_item(result: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten a ranked result into a clean evidence dict."""
    return {
        "text":  result.get("chunk", ""),
        "pmid":  result.get("pmid", ""),
        "title": result.get("title", ""),
        "score": result.get("rerank_score", 0.0),
        "score_type": "raw_cross_encoder_score",
    }


# ──────────────────────────────────────────────────────────────────────────────
#  Primary assembler
# ──────────────────────────────────────────────────────────────────────────────

def assemble_payload(
    query:             str,
    ranked_results:    List[Dict[str, Any]],
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
    physics_vector:    Optional[Dict[str, Any]] = None,
    rag_status:        str  = CM_RAG_NULL,
    clinical_context:  Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Orchestrate the assembly of a structured JSON payload.

    Process:
    1. RAG threshold filtering → deduplication → sorting
    2. Build confidence_matrix (per-engine granular status)
    3. Derive global status via the confidence matrix logic gate
    4. Attach directives / notes for VUS-class results

    Args:
        query:                Original search query string.
        ranked_results:       Top-K ranked chunks from vector_engine.
        confidence_threshold: Minimum rerank_score threshold (default 0.7).
        physics_vector:       Dict from ``*_physics.json``; enables VUS promotion.
        rag_status:           One of CM_RAG_SUCCESS / CM_RAG_NULL / CM_RAG_TIMEOUT.
                              Callers derive this from the retrieval outcome.
        clinical_context:     Dict from ``*_context.json``; used to populate the
                              clinical_context cell of the confidence_matrix.

    Returns:
        Structured payload dict.  Always contains:
          status, confidence_matrix, query, evidence
        VUS-class results additionally contain:
          note, physics_violations, llm_directive (STRUCTURAL_DISCOVERY_VUS only)
    """
    # ── Step 1: RAG processing ────────────────────────────────────────────────
    filtered, low_confidence = filter_by_threshold(ranked_results, threshold=confidence_threshold)
    deduplicated = deduplicate_by_pmid(filtered)
    sorted_results = sort_by_score(deduplicated, descending=True)
    evidence = [construct_evidence_item(r) for r in sorted_results]

    # ── Step 2: Confidence matrix ─────────────────────────────────────────────
    matrix = build_confidence_matrix(physics_vector, rag_status, clinical_context)

    # ── Step 3: Global status ─────────────────────────────────────────────────
    status = derive_global_status(
        matrix,
        has_evidence=bool(evidence),
        low_confidence=low_confidence,
        physics_vector=physics_vector,
    )

    # ── Step 4: Assemble base payload ─────────────────────────────────────────
    payload: Dict[str, Any] = {
        "status":            status,
        "confidence_matrix": matrix,
        "query":             query,
        "evidence_score_type": "raw_cross_encoder_score",
        "evidence":          evidence,
    }

    # ── Step 5: Attach VUS artefacts ─────────────────────────────────────────
    if status == "STRUCTURAL_DISCOVERY_VUS" and physics_vector:
        is_severe, violations, n_viol = evaluate_physics_severity(physics_vector)
        payload["note"]             = build_vus_note(physics_vector, violations, status="STRUCTURAL_DISCOVERY_VUS")
        payload["llm_directive"]    = STRUCTURAL_DISCOVERY_VUS_DIRECTIVE
        payload["physics_violations"] = {
            "count":   n_viol,
            "details": violations,
        }

    elif status == "PREDICTED_PATHOGENIC_VUS" and physics_vector:
        is_severe, violations, n_viol = evaluate_physics_severity(physics_vector)
        payload["note"]             = build_vus_note(physics_vector, violations, status="PREDICTED_PATHOGENIC_VUS")
        payload["physics_violations"] = {
            "count":   n_viol,
            "details": violations,
        }

    return payload


# ──────────────────────────────────────────────────────────────────────────────
#  I/O helpers
# ──────────────────────────────────────────────────────────────────────────────

def save_payload(payload: Dict[str, Any], output_path: str = OUTPUT_PATH) -> str:
    """Persist payload to JSON file; returns path written."""
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return output_path


def run(
    query:            str,
    ranked_results:   List[Dict[str, Any]],
    output_path:      Optional[str] = None,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
    physics_vector:   Optional[Dict[str, Any]] = None,
    rag_status:       str = CM_RAG_NULL,
    clinical_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Complete pipeline: assemble, print summary, and save payload.

    Args:
        query:            Search query.
        ranked_results:   Top-K reranked results from vector_engine.
        output_path:      Optional custom output file path.
        physics_vector:   Optional physics dict for VUS promotion.
        rag_status:       Retrieval outcome hint (default: NULL_RESULTS).
        clinical_context: Optional clinical context dict.

    Returns:
        The assembled payload dict.
    """
    payload = assemble_payload(
        query,
        ranked_results,
        confidence_threshold=confidence_threshold,
        physics_vector=physics_vector,
        rag_status=rag_status,
        clinical_context=clinical_context,
    )

    final_path = output_path or OUTPUT_PATH
    saved_path = save_payload(payload, final_path)

    status = payload["status"]
    print(f"[OK] Payload assembled and saved: {saved_path}")
    print(f"   - Status:         {status}")
    print(f"   - Evidence items: {len(payload['evidence'])}")
    matrix = payload.get("confidence_matrix", {})
    print(f"   - Physics engine: {matrix.get('physics_engine', '?')}")
    print(f"   - RAG:            {matrix.get('literature_rag', '?')}")
    print(f"   - Clinical:       {matrix.get('clinical_context', '?')}")
    if status in {"STRUCTURAL_DISCOVERY_VUS", "PREDICTED_PATHOGENIC_VUS"}:
        n = payload.get("physics_violations", {}).get("count", 0)
        print(f"   - Physics violations (severe): {n}")

    return payload


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        print(f"Running assemble_payload with query: {sys.argv[1]}")
    else:
        print("Usage: python assemble_payload.py '<query>'")
        print("Note: This is typically called from the orchestration controller")
