"""
Phase 8 — Multi-Modal LLM Reasoning Engine (OpenRouter Integration)

Connects:
  - Phase 2: Structural Physics (ΔV, ΔH, ΔQ, ΔSASA, DSSP, pLDDT)
  - Phase 7: Clinical Context (ClinVar, AlphaMissense, dbSNP)
  - Phase 6: Dual-RAG Literature (Bi-Encoder + Cross-Encoder Reranked Chunks)
  
Generates:
  1. Unstructured Output: Comprehensive Clinical Verdict & Molecular Reasoning Narrative
  2. Structured Output: Executive Bottom Line, Molecular Mechanism, Clinical Phenotypes, Experimental Highlights

Integrity Guarantees:
  - Strict server-side PMID validation across all output fields (free-text narrative, cited_pmids, experimental_highlights).
  - No fabricated defaults on missing inputs: missing data remains missing (VUS / INSUFFICIENT_EVIDENCE).
  - ClinVar exact-variant matches are preserved and clearly labeled (e.g. CLINVAR_PATHOGENIC).
  - Multi-tier API key rotation and model cascade.
"""

from __future__ import annotations

import os
import re
import json
import logging
from typing import Any, Dict, List, Optional, Set
import httpx

logger = logging.getLogger(__name__)

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

DEFAULT_MODELS_CASCADE = [
    "openrouter/free",
    "z-ai/glm-5.2:free",
    "nvidia/nemotron-3.5-lightning:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "google/gemma-4-31b-it:free",
]


def get_openrouter_api_keys() -> List[str]:
    """
    Retrieve all OpenRouter API keys from environment or local .env file.
    Supports OPENROUTER_API_KEYS (comma or newline separated) and OPENROUTER_API_KEY.
    """
    keys: List[str] = []

    # 1. Check environment variables
    env_keys = os.getenv("OPENROUTER_API_KEYS")
    if env_keys:
        for k in re.split(r"[,\n;]+", env_keys):
            k = k.strip().strip('"').strip("'")
            if k and k not in keys:
                keys.append(k)

    single_key = os.getenv("OPENROUTER_API_KEY")
    if single_key:
        single_key = single_key.strip().strip('"').strip("'")
        if single_key and single_key not in keys:
            keys.append(single_key)

    # 2. Check local .env file
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.isfile(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("OPENROUTER_API_KEYS="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        for k in re.split(r"[,\n;]+", val):
                            k = k.strip()
                            if k and k not in keys:
                                keys.append(k)
                    elif line.startswith("OPENROUTER_API_KEY="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val and val not in keys:
                            keys.append(val)
        except Exception as e:
            logger.warning(f"Failed to read .env file for keys: {e}")

    return keys


def get_preferred_model() -> str:
    """Retrieve preferred model from environment or fallback cascade."""
    model = os.getenv("OPENROUTER_MODEL")
    if model and model.strip():
        return model.strip()
        
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.isfile(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("OPENROUTER_MODEL="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            return val
        except Exception:
            pass

    return DEFAULT_MODELS_CASCADE[0]


def clean_and_parse_json(raw_text: str) -> Optional[Dict[str, Any]]:
    """Robustly extract and parse JSON object from LLM response text."""
    if not isinstance(raw_text, str):
        return None
        
    # 1. Strip think / internal chain-of-thought blocks
    text = re.sub(r'<think>.*?</think>', '', raw_text, flags=re.DOTALL).strip()
    
    # 2. Strip markdown code fences
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # 3. Direct parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # 4. Extract outermost JSON object with regex
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        candidate = match.group(1).strip()
        try:
            return json.loads(candidate)
        except Exception:
            pass

    return None


def sanitize_narrative_pmids(text: str, valid_pmids: Set[str]) -> str:
    """
    Sanitize PMIDs embedded in free-text narrative.
    Removes or flags citations to PMIDs not in the retrieved evidence set.
    """
    if not text or not isinstance(text, str):
        return ""

    # Match patterns like [PMID: 123456], [PMID 123456], PMID: 123456, PMID 123456
    def _replace_pmid(match: re.Match) -> str:
        full_match = match.group(0)
        pmid_digits = match.group(1)
        if pmid_digits in valid_pmids:
            return f"[PMID: {pmid_digits}]"
        # If PMID was not in retrieved evidence, remove the ungrounded citation tag
        return ""

    pattern = r"\[?\bPMID:?\s*(\d{4,10})\b\]?"
    sanitized = re.sub(pattern, _replace_pmid, text)
    # Clean up double spaces or dangling punctuation from removed citations
    sanitized = re.sub(r"\s{2,}", " ", sanitized)
    sanitized = re.sub(r"\s+([.,;:!?])", r"\1", sanitized)
    return sanitized.strip()


def validate_and_sanitize_reasoning(
    unstructured_verdict: str,
    structured_data: Dict[str, Any],
    evidence: List[Dict[str, Any]],
) -> tuple[str, Dict[str, Any]]:
    """
    Strict server-side validation and sanitization of LLM output.
    Validates all cited PMIDs in unstructured narrative, cited_pmids array,
    and experimental highlights against retrieved evidence.
    """
    valid_pmids: Set[str] = {
        str(item.get("pmid")).strip()
        for item in evidence
        if item.get("pmid") and str(item.get("pmid")).strip().isdigit()
    }

    # 1. Sanitize free-text narrative
    sanitized_narrative = sanitize_narrative_pmids(unstructured_verdict, valid_pmids)

    # 2. Sanitize structured_data
    if not isinstance(structured_data, dict):
        structured_data = {}

    raw_cited = structured_data.get("cited_pmids", [])
    if isinstance(raw_cited, list):
        sanitized_cited = [
            str(p).strip() for p in raw_cited
            if str(p).strip() in valid_pmids
        ]
    else:
        sanitized_cited = []
    structured_data["cited_pmids"] = sanitized_cited

    # 3. Sanitize experimental highlights
    raw_highlights = structured_data.get("experimental_highlights", [])
    sanitized_highlights = []
    if isinstance(raw_highlights, list):
        for h in raw_highlights:
            if isinstance(h, dict):
                h_pmid = str(h.get("pmid", "")).strip() if h.get("pmid") else None
                if h_pmid and h_pmid in valid_pmids:
                    sanitized_highlights.append({
                        "system": h.get("system", "Experimental Model"),
                        "finding": h.get("finding", "Biomedical finding"),
                        "pmid": h_pmid,
                    })
                else:
                    # Keep highlight but remove unsupported PMID
                    sanitized_highlights.append({
                        "system": h.get("system", "Experimental Model"),
                        "finding": h.get("finding", "Biomedical finding"),
                        "pmid": None,
                    })
    structured_data["experimental_highlights"] = sanitized_highlights

    return sanitized_narrative, structured_data


def construct_reasoning_prompt(
    gene: str,
    variant: str,
    physics_data: Optional[Dict[str, Any]],
    context_data: Optional[Dict[str, Any]],
    evidence: List[Dict[str, Any]],
    status: Optional[str] = None,
) -> str:
    """Construct a rigorous, grounded clinical reasoning prompt."""
    deltas = physics_data.get("deltas", {}) if isinstance(physics_data, dict) else {}
    struct_ctx = physics_data.get("structural_context_wt", {}) if isinstance(physics_data, dict) else {}
    dv = deltas.get("delta_volume", "Unavailable")
    dq = deltas.get("delta_charge", "Unavailable")
    dh = deltas.get("delta_hydrophobicity", "Unavailable")
    sasa = struct_ctx.get("sasa", "Unavailable")
    exposure = struct_ctx.get("exposure", "Unavailable")
    sec_struct = struct_ctx.get("secondary_structure", "Unavailable")
    plddt = struct_ctx.get("plddt", "Unavailable")

    clinvar = context_data.get("clinvar", {}) if isinstance(context_data, dict) else {}
    clin_sig = clinvar.get("clinical_significance", "Not found in ClinVar")
    conditions = clinvar.get("conditions", [])
    if isinstance(conditions, list):
        conditions_str = ", ".join(conditions) if conditions else "None specified in ClinVar"
    else:
        conditions_str = str(conditions)

    am = context_data.get("alphamissense_sniper", {}) if isinstance(context_data, dict) else {}
    am_score = am.get("score", "Unavailable")
    am_class = am.get("class", "Unavailable")

    evidence_blocks = []
    for i, item in enumerate(evidence[:5], 1):
        pmid = item.get("pmid", "Unknown")
        title = item.get("title", "Untitled")
        score = item.get("score", item.get("rerank_score", 0.0))
        text = item.get("text", item.get("chunk", "")).strip()
        evidence_blocks.append(
            f"[Paper {i} | PMID: {pmid} | Relevance Score: {score}]\n"
            f"Title: {title}\n"
            f"Excerpt: {text}"
        )
    evidence_str = "\n\n".join(evidence_blocks) if evidence_blocks else "No literature evidence retrieved."

    prompt = f"""You are a senior clinical bioinformatician and structural biologist specializing in neurodegenerative diseases.
Analyze the following multi-modal evidence for the missense variant {gene} {variant}.

=== 1. STRUCTURAL BIOPHYSICS LAYER (Phase 2) ===
- Volume Delta (ΔV): {dv} Å³
- Charge Delta (ΔQ): {dq}
- Hydrophobicity Shift (ΔH): {dh}
- Solvent Accessible Surface Area (SASA): {sasa} Å² ({exposure})
- Secondary Structure Context: {sec_struct}
- AlphaFold Confidence (pLDDT): {plddt}

=== 2. CLINICAL BENCHMARK CONTEXT (Phase 7) ===
- ClinVar Clinical Significance: {clin_sig}
- Associated Phenotypes / Diseases: {conditions_str}
- AlphaMissense Pathogenicity: Score {am_score} ({am_class})

=== 3. RERANKED PEER-REVIEWED LITERATURE (Phase 6 Dual-RAG) ===
{evidence_str}

=== INSTRUCTIONS ===
Generate a dual-output clinical synthesis strictly adhering to the JSON schema below.
Strict Grounding Rules:
1. Only make claims supported by the structural physics, clinical databases, or cited PMIDs.
2. If data is unavailable, explicitly state that evidence is unavailable; NEVER invent metrics or phenotypes.
3. Only cite PMIDs that appear in the supplied literature above. Do not invent PMIDs.

JSON Schema:
{{
  "unstructured_verdict": "Detailed multi-paragraph clinical reasoning narrative summarizing the consensus between structural physics, clinical database classifications, and experimental literature. Cite PMIDs like [PMID: 12345678] only from the supplied list.",
  "structured_data": {{
    "executive_bottom_line": "One punchy sentence summarizing the definitive structural and clinical impact of this variant based only on available data.",
    "molecular_mechanism": {{
      "key_disruption": "Short title (e.g. Steric Bulk & Helical Destabilization, or Data Unavailable)",
      "biophysical_rationale": "Clear explanation of how ΔV, ΔH, ΔQ, or SASA affect protein folding, or state if unavailable.",
      "affected_motif": "Specific structural region or domain affected, or Unavailable"
    }},
    "clinical_phenotypes": [
      {{ "disease": "Disease Name", "confidence": "Definitive / Strong / Moderate / Uncertain" }}
    ],
    "experimental_highlights": [
      {{ "system": "Experimental Model", "finding": "Key biological finding from supplied paper", "pmid": "PMID from supplied list" }}
    ],
    "verdict_badge": "PATHOGENIC / LIKELY_PATHOGENIC / VUS / BENIGN / INSUFFICIENT_EVIDENCE",
    "confidence_assessment": "High (Multi-Modal Consensus) / Moderate / VUS / Low (Insufficient Evidence)",
    "cited_pmids": ["List of PMIDs cited from the supplied list"]
  }}
}}

Output ONLY the JSON object.
"""
    return prompt


def generate_reasoning(
    gene: str,
    variant: str,
    physics_data: Optional[Dict[str, Any]] = None,
    context_data: Optional[Dict[str, Any]] = None,
    evidence: Optional[List[Dict[str, Any]]] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute Phase 8 LLM Reasoning via OpenRouter with API key pool rotation and multi-model cascading.
    Validates and sanitizes all PMIDs against retrieved evidence before returning.
    """
    evidence = evidence or []
    api_keys = get_openrouter_api_keys()

    if not api_keys:
        logger.warning("No OpenRouter API keys found. Using local deterministic reasoning engine.")
        return _fallback_reasoning(gene, variant, physics_data, context_data, evidence, status, "Local Deterministic Synthesis (No API Keys)")

    prompt = construct_reasoning_prompt(gene, variant, physics_data, context_data, evidence, status)
    
    preferred = get_preferred_model()
    models_to_try = [preferred] + [m for m in DEFAULT_MODELS_CASCADE if m != preferred]

    # Loop through model hierarchy
    for model_id in models_to_try:
        for key_idx, api_key in enumerate(api_keys, 1):
            key_preview = f"...{api_key[-6:]}" if len(api_key) > 6 else "key"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "http://localhost:5173",
                "X-Title": "NeuroCapstone Research Platform",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model_id,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a clinical bioinformatics reasoning engine. You output strictly valid JSON conforming to the requested schema without conversational filler.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 2500,
            }

            try:
                logger.info(f"Querying [{model_id}] using API Key {key_idx}/{len(api_keys)} ({key_preview})...")
                with httpx.Client(timeout=25.0) as client:
                    response = client.post(OPENROUTER_API_URL, headers=headers, json=payload)

                if response.status_code == 200:
                    data = response.json()
                    choices = data.get("choices")
                    if choices and len(choices) > 0:
                        raw_content = choices[0].get("message", {}).get("content", "")
                        parsed = clean_and_parse_json(raw_content)

                        if parsed:
                            unstructured = parsed.get("unstructured_verdict", parsed.get("grounded_summary", ""))
                            structured = parsed.get("structured_data", parsed)
                            
                            # Server-side PMID validation & sanitization
                            sanitized_narrative, sanitized_structured = validate_and_sanitize_reasoning(
                                unstructured, structured, evidence
                            )

                            logger.info(f"OpenRouter reasoning successfully generated via [{model_id}] with Key #{key_idx}.")
                            return {
                                "unstructured_verdict": sanitized_narrative,
                                "structured_data": sanitized_structured,
                                "model_used": model_id,
                                "source": f"OpenRouter ({model_id} via Key #{key_idx})",
                            }

                if response.status_code in (402, 429):
                    logger.warning(f"Key #{key_idx} exhausted/rate-limited on {model_id} (Status {response.status_code}). Rotating to next key in pool...")
                    continue
                else:
                    logger.warning(f"Model {model_id} with Key #{key_idx} returned {response.status_code}. Trying next key...")
                    continue

            except Exception as exc:
                logger.warning(f"Exception querying {model_id} with Key #{key_idx}: {exc}. Rotating to next key...")
                continue

        logger.warning(f"All {len(api_keys)} API key(s) exhausted on [{model_id}]. Cascading to next model tier...")

    logger.warning("All models and API keys exhausted. Utilizing local deterministic reasoning engine.")
    return _fallback_reasoning(gene, variant, physics_data, context_data, evidence, status, "Local Deterministic Synthesis (All Keys & Models Exhausted)")


def _fallback_reasoning(
    gene: str,
    variant: str,
    physics_data: Optional[Dict[str, Any]],
    context_data: Optional[Dict[str, Any]],
    evidence: List[Dict[str, Any]],
    status: Optional[str],
    source_note: str,
) -> Dict[str, Any]:
    """
    Evidence-grounded deterministic fallback.
    Never hallucinates missing data:
    - ClinVar results preserved ONLY when exact match exists (e.g. CLINVAR_PATHOGENIC).
    - Missing clinical or physics data explicitly reported as unavailable.
    - Defaults to VUS / INSUFFICIENT_EVIDENCE when evidence is absent.
    """
    evidence = evidence or []
    has_physics = isinstance(physics_data, dict) and bool(physics_data.get("deltas"))
    deltas = physics_data.get("deltas", {}) if has_physics else {}
    struct_ctx = physics_data.get("structural_context_wt", {}) if has_physics else {}

    has_context = isinstance(context_data, dict) and bool(context_data)
    clinvar = context_data.get("clinvar", {}) if has_context else {}
    am = context_data.get("alphamissense_sniper", {}) if has_context else {}

    # Exact ClinVar matching check
    is_exact_clinvar = bool(
        clinvar.get("variant_match") is True
        or clinvar.get("scope") == "exact_variant"
    )
    raw_clin_sig = clinvar.get("clinical_significance") if is_exact_clinvar else None
    
    conditions = clinvar.get("conditions", []) if (is_exact_clinvar and isinstance(clinvar.get("conditions"), list)) else []
    conditions_str = ", ".join(conditions) if conditions else "No disease associations cataloged"

    am_score = am.get("score")
    am_class = am.get("class")

    # Determine grounded verdict badge
    if raw_clin_sig:
        sig_lower = raw_clin_sig.lower()
        if "pathogenic" in sig_lower:
            verdict_badge = "CLINVAR_PATHOGENIC"
            conf_assessment = "High (ClinVar Exact Match)"
        elif "benign" in sig_lower:
            verdict_badge = "CLINVAR_BENIGN"
            conf_assessment = "High (ClinVar Exact Match)"
        else:
            verdict_badge = f"CLINVAR_{raw_clin_sig.upper().replace(' ', '_')}"
            conf_assessment = "Moderate (ClinVar Classification)"
    elif am_class and am_class.lower() == "pathogenic":
        verdict_badge = "ALPHAMISSENSE_PATHOGENIC"
        conf_assessment = "Moderate (AlphaMissense Prediction)"
    else:
        verdict_badge = "VUS / INSUFFICIENT_EVIDENCE"
        conf_assessment = "Low / Insufficient Multi-Modal Evidence"

    # Physics values
    dv = str(deltas.get("delta_volume", "Unavailable"))
    dq = str(deltas.get("delta_charge", "Unavailable"))
    dh = str(deltas.get("delta_hydrophobicity", "Unavailable"))
    sasa = str(struct_ctx.get("sasa", "Unavailable"))
    exposure = str(struct_ctx.get("exposure", "Unavailable"))
    sec_struct = str(struct_ctx.get("secondary_structure", "Unavailable"))

    # Valid retrieved PMIDs
    valid_pmids = [
        str(item.get("pmid")).strip()
        for item in evidence
        if item.get("pmid") and str(item.get("pmid")).strip().isdigit()
    ]
    cite_str = " ".join([f"[PMID: {p}]" for p in valid_pmids[:3]]) if valid_pmids else ""

    # Grounded narrative construction
    narrative_paragraphs = []
    
    if raw_clin_sig:
        narrative_paragraphs.append(
            f"Clinical evidence for {gene} {variant} from NCBI ClinVar classifies the variant as {raw_clin_sig} ({conditions_str})."
        )
    elif am_score is not None:
        narrative_paragraphs.append(
            f"Clinical database records are absent in ClinVar for {gene} {variant}. AlphaMissense computational analysis yields a pathogenicity score of {am_score} ({am_class})."
        )
    else:
        narrative_paragraphs.append(
            f"Clinical database annotations and computational pathogenicity scores are currently unavailable for {gene} {variant} in ClinVar, LOVD, and AlphaMissense."
        )

    if has_physics:
        narrative_paragraphs.append(
            f"Structural biophysical profiling indicates a volume delta ΔV = {dv} Å³, charge shift ΔQ = {dq}, "
            f"and hydrophobicity shift ΔH = {dh} within a {sec_struct} context (SASA = {sasa} Å², {exposure})."
        )
    else:
        narrative_paragraphs.append(
            f"Structural biophysics metrics (volume delta, SASA, secondary structure context) are unavailable for {gene} {variant}."
        )

    if valid_pmids:
        narrative_paragraphs.append(
            f"The literature retrieval layer retrieved {len(valid_pmids)} peer-reviewed evidence item(s) {cite_str} "
            f"relevant to {gene} {variant}."
        )
    else:
        narrative_paragraphs.append(
            f"No peer-reviewed literature evidence was retrieved for {gene} {variant}."
        )

    unstructured_verdict = "\n\n".join(narrative_paragraphs)

    # Executive bottom line
    if raw_clin_sig:
        bottom_line = f"{gene} {variant} is classified as {raw_clin_sig} in ClinVar ({conditions_str})."
    elif has_physics:
        bottom_line = f"{gene} {variant} exhibits a {dv} Å³ volume shift; clinical classifications remain uncharacterized."
    else:
        bottom_line = f"Insufficient multi-modal evidence available to classify {gene} {variant} definitively."

    # Molecular mechanism
    if has_physics:
        mol_mech = {
            "key_disruption": f"Residue Perturbation (ΔV: {dv} Å³, ΔH: {dh})",
            "biophysical_rationale": f"Substitution alters local biophysics (ΔV = {dv} Å³, ΔH = {dh}, SASA = {sasa} Å²).",
            "affected_motif": f"{gene} (Residue {variant})"
        }
    else:
        mol_mech = {
            "key_disruption": "Biophysical Disruption Unavailable",
            "biophysical_rationale": "No structural model or biophysical calculations were returned.",
            "affected_motif": "Unavailable"
        }

    # Clinical phenotypes
    if conditions:
        clinical_phenotypes = [
            {"disease": cond, "confidence": "Definitive" if i == 0 else "Strong"}
            for i, cond in enumerate(conditions[:3])
        ]
    else:
        clinical_phenotypes = [
            {"disease": "Unspecified / Insufficient Phenotype Data", "confidence": "Uncertain"}
        ]

    # Experimental highlights from genuine evidence only
    experimental_highlights = [
        {
            "system": item.get("title", "Biomedical Study")[:50] + "...",
            "finding": item.get("text", item.get("chunk", ""))[:120] + "...",
            "pmid": str(item.get("pmid")) if item.get("pmid") else None
        }
        for item in evidence[:3] if item.get("title") or item.get("text")
    ]

    structured_data = {
        "executive_bottom_line": bottom_line,
        "molecular_mechanism": mol_mech,
        "clinical_phenotypes": clinical_phenotypes,
        "experimental_highlights": experimental_highlights,
        "verdict_badge": verdict_badge,
        "confidence_assessment": conf_assessment,
        "cited_pmids": valid_pmids,
    }

    return {
        "unstructured_verdict": unstructured_verdict,
        "structured_data": structured_data,
        "model_used": "Deterministic Synthesis Engine",
        "source": source_note,
    }
