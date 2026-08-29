import sys
import os
import json
from typing import Any, Dict, Optional, List

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool


# ============================================================================
# PROJECT PATH
# ============================================================================

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(
    os.path.join(CURRENT_DIR, "..", "..")
)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ============================================================================
# SCIENTIFIC PIPELINE
# ============================================================================

try:
    from pipeline import run_pipeline
except ImportError as exc:
    raise ImportError(
        f"Could not import 'pipeline' from project root "
        f"({PROJECT_ROOT}). Ensure pipeline.py exists."
    ) from exc


# ============================================================================
# EVIDENCE PIPELINE
# ============================================================================

try:
    from orchestration import run_full_pipeline
except ImportError as exc:
    raise ImportError(
        f"Could not import 'run_full_pipeline' from orchestration.py "
        f"({PROJECT_ROOT})."
    ) from exc


# ============================================================================
# FASTAPI
# ============================================================================

app = FastAPI(
    title="NeuroCapstone Local API",
    description="Local API adapter for the Protein Mutation Analysis pipeline.",
    version="1.0.0",
)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# REQUEST / RESPONSE MODELS
# ============================================================================

class AnalyzeRequest(BaseModel):
    gene: str = Field(
        ...,
        min_length=1,
        description="Gene symbol, e.g. SNCA",
    )

    variant: str = Field(
        ...,
        min_length=1,
        description="Variant specification, e.g. A53T",
    )


class LiteratureEvidence(BaseModel):
    text: str
    pmid: str
    title: str
    score: float
    score_type: str


class AnalyzeResponse(BaseModel):
    gene: str
    variant: str

    # Actual global pipeline classification
    status: Optional[str] = None

    # Actual per-engine confidence information
    confidence_matrix: Optional[Dict[str, Any]] = None

    context_data: Optional[Dict[str, Any]] = None
    physics_data: Optional[Dict[str, Any]] = None
    pdb_content: Optional[str] = None

    # Top reranked literature evidence
    evidence: List[LiteratureEvidence] = []

    # Human-readable evidence synthesis
    clinical_narrative: Optional[str] = None

    warnings: Optional[Dict[str, str]] = None


# ============================================================================
# HELPERS
# ============================================================================

def extract_evidence_from_payload(
    payload: Any,
) -> List[Dict[str, Any]]:
    """
    Extract the top five evidence records produced by assemble_payload.
    No evidence is generated here.
    """

    if not isinstance(payload, dict):
        return []

    evidence = payload.get("evidence")

    if not isinstance(evidence, list):
        return []

    cleaned: List[Dict[str, Any]] = []

    for item in evidence[:5]:

        if not isinstance(item, dict):
            continue

        text = item.get("text")

        if text is None:
            text = item.get("chunk", "")

        pmid = item.get("pmid", "")
        title = item.get(
            "title",
            "Untitled publication",
        )

        score = item.get("score")

        if score is None:
            score = item.get(
                "rerank_score",
                0.0,
            )

        score_type = item.get(
            "score_type",
            "raw_cross_encoder_score",
        )

        try:
            score_value = float(score)
        except (TypeError, ValueError):
            score_value = 0.0

        cleaned.append(
            {
                "text": str(text or ""),
                "pmid": str(pmid or ""),
                "title": str(
                    title or "Untitled publication"
                ),
                "score": score_value,
                "score_type": str(score_type),
            }
        )

    return cleaned


def extract_clinical_narrative(
    context_data: Any,
) -> Optional[str]:
    """
    Use a narrative if the scientific context pipeline already provides one.

    This function deliberately does not invent clinical information.
    """

    if not isinstance(context_data, dict):
        return None

    possible_keys = [
        "clinical_narrative",
        "clinical_interpretation",
        "narrative",
        "evidence_synthesis",
    ]

    for key in possible_keys:

        value = context_data.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


def build_evidence_synthesis(
    gene: str,
    variant: str,
    status_value: Optional[str],
    confidence_matrix: Optional[Dict[str, Any]],
    context_data: Optional[Dict[str, Any]],
    physics_data: Optional[Dict[str, Any]],
    evidence: List[Dict[str, Any]],
) -> Optional[str]:
    """
    Build a human-readable synthesis strictly from returned pipeline data.

    This is a deterministic evidence-synthesis layer.
    It does not fabricate clinical facts or external claims.
    """

    context = context_data or {}
    physics = physics_data or {}
    matrix = confidence_matrix or {}

    paragraphs: List[str] = []

    # ------------------------------------------------------------------------
    # Overall classification
    # ------------------------------------------------------------------------

    if status_value:
        paragraphs.append(
            f"The integrated pipeline classified {gene} {variant} "
            f"as {status_value.replace('_', ' ')}."
        )

    # ------------------------------------------------------------------------
    # Clinical evidence
    # ------------------------------------------------------------------------

    clinical_parts: List[str] = []

    clinvar = context.get("clinvar")

    if isinstance(clinvar, dict):

        significance = clinvar.get(
            "clinical_significance"
        )

        if significance:
            clinical_parts.append(
                f"ClinVar reports {significance}."
            )

        conditions = clinvar.get("conditions")

        if isinstance(conditions, list):

            clean_conditions = [
                str(condition).strip()
                for condition in conditions
                if str(condition).strip()
            ]

            if clean_conditions:
                unique_conditions = list(
                    dict.fromkeys(clean_conditions)
                )

                clinical_parts.append(
                    "Reported associated conditions include "
                    + ", ".join(unique_conditions[:4])
                    + "."
                )

    alphamissense = context.get(
        "alphamissense_sniper"
    )

    if isinstance(alphamissense, dict):

        score = alphamissense.get("score")
        verdict = alphamissense.get("verdict")

        if score is not None and verdict:
            try:
                clinical_parts.append(
                    f"AlphaMissense reports a score of "
                    f"{float(score):.4f} with a "
                    f"{verdict} interpretation."
                )
            except (TypeError, ValueError):
                clinical_parts.append(
                    f"AlphaMissense reports a "
                    f"{verdict} interpretation."
                )

    if clinical_parts:

        paragraphs.append(
            "Clinical and database evidence: "
            + " ".join(clinical_parts)
        )

    # ------------------------------------------------------------------------
    # Structural evidence
    # ------------------------------------------------------------------------

    deltas = physics.get("deltas")

    structural_parts: List[str] = []

    if isinstance(deltas, dict):

        if deltas.get("delta_volume") is not None:
            try:
                value = float(
                    deltas["delta_volume"]
                )

                structural_parts.append(
                    f"volume change ΔV = {value:+.1f} Å³"
                )
            except (TypeError, ValueError):
                pass

        if deltas.get("delta_charge") is not None:
            try:
                value = float(
                    deltas["delta_charge"]
                )

                structural_parts.append(
                    f"charge shift ΔQ = {value:+.1f}"
                )
            except (TypeError, ValueError):
                pass

        if deltas.get(
            "delta_hydrophobicity"
        ) is not None:

            try:
                value = float(
                    deltas["delta_hydrophobicity"]
                )

                structural_parts.append(
                    f"hydrophobicity change ΔH = {value:+.1f}"
                )
            except (TypeError, ValueError):
                pass

    structural_context = physics.get(
        "structural_context_wt"
    )

    if isinstance(structural_context, dict):

        exposure = structural_context.get(
            "exposure"
        )

        sasa = structural_context.get(
            "sasa"
        )

        secondary = structural_context.get(
            "secondary_structure"
        )

        if exposure:
            structural_parts.append(
                f"the residue is classified as "
                f"{exposure.lower()}."
            )

        if sasa is not None:
            try:
                structural_parts.append(
                    f"SASA is "
                    f"{float(sasa):.2f} Å²."
                )
            except (TypeError, ValueError):
                pass

        if secondary:
            structural_parts.append(
                f"The reported secondary-structure context "
                f"is {secondary}."
            )

    if structural_parts:

        paragraphs.append(
            "Structural evidence: "
            + " ".join(structural_parts)
        )

    # ------------------------------------------------------------------------
    # Literature evidence
    # ------------------------------------------------------------------------

    if evidence:

        top_titles = [
            item.get("title", "").strip()
            for item in evidence[:3]
            if item.get("title")
        ]

        literature_text = (
            f"The literature retrieval layer returned "
            f"{len(evidence)} ranked evidence chunk"
            f"{'s' if len(evidence) != 1 else ''}."
        )

        if top_titles:

            literature_text += (
                " The highest-ranked retrieved publications "
                "include: "
                + "; ".join(top_titles)
                + "."
            )

        paragraphs.append(
            literature_text
        )

    else:

        rag_status = matrix.get(
            "literature_rag"
        )

        if rag_status in {
            "NULL_RESULTS",
            "TIMEOUT_ERROR",
        }:

            paragraphs.append(
                "The literature retrieval layer did not "
                "return ranked evidence for this analysis."
            )

    # ------------------------------------------------------------------------
    # Evidence limitation
    # ------------------------------------------------------------------------

    paragraphs.append(
        "This interpretation summarizes the evidence returned "
        "by the computational pipeline and should not be treated "
        "as a standalone clinical diagnosis."
    )

    return "\n\n".join(paragraphs)


def find_physics_path(
    physics_json_path: Optional[str],
) -> Optional[str]:

    if not physics_json_path:
        return None

    if os.path.isfile(physics_json_path):
        return os.path.abspath(
            physics_json_path
        )

    candidate = os.path.join(
        PROJECT_ROOT,
        physics_json_path,
    )

    if os.path.isfile(candidate):
        return os.path.abspath(candidate)

    return None


# ============================================================================
# ROUTES
# ============================================================================

@app.get("/health")
def health_check():

    return {
        "status": "ok",
        "backend": "active",
        "project_root": PROJECT_ROOT,
    }


@app.post(
    "/analyze",
    response_model=AnalyzeResponse,
)
async def analyze_variant(
    payload: AnalyzeRequest,
):

    gene = payload.gene.strip()
    variant = payload.variant.strip()

    if not gene or not variant:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gene and variant are required.",
        )

    warnings: Dict[str, str] = {}

    # ========================================================================
    # 1. STRUCTURE + CONTEXT + PHYSICS
    # ========================================================================

    try:

        pdb_path, context_data, physics_json_path = (
            await run_in_threadpool(
                run_pipeline,
                gene,
                variant,
            )
        )

    except Exception as exc:

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Scientific pipeline execution failed: "
                f"{str(exc)}"
            ),
        ) from exc

    # ========================================================================
    # 2. PHYSICS
    # ========================================================================

    physics_data = None

    if physics_json_path:

        if os.path.isfile(
            physics_json_path
        ):

            try:

                with open(
                    physics_json_path,
                    "r",
                    encoding="utf-8",
                ) as file:

                    physics_data = json.load(
                        file
                    )

            except Exception as exc:

                warnings["physics_error"] = (
                    f"Failed to parse physics JSON: {str(exc)}"
                )

        else:

            warnings["physics_missing"] = (
                f"Physics JSON file missing at: "
                f"{physics_json_path}"
            )

    else:

        warnings["physics_missing"] = (
            "Pipeline returned no physics JSON path."
        )

    # ========================================================================
    # 3. PDB
    # ========================================================================

    pdb_content = None

    if pdb_path:

        if os.path.isfile(pdb_path):

            try:

                with open(
                    pdb_path,
                    "r",
                    encoding="utf-8",
                ) as file:

                    pdb_content = file.read()

            except Exception as exc:

                warnings["pdb_error"] = (
                    f"Failed to read PDB file: {str(exc)}"
                )

        else:

            warnings["pdb_missing"] = (
                f"PDB file missing at: {pdb_path}"
            )

    else:

        warnings["pdb_missing"] = (
            "Pipeline returned no PDB path."
        )

    # ========================================================================
    # 4. LITERATURE + PAYLOAD
    # ========================================================================

    evidence: List[Dict[str, Any]] = []

    pipeline_status: Optional[str] = None

    confidence_matrix: Optional[
        Dict[str, Any]
    ] = None

    payload_note: Optional[str] = None

    try:

        physics_path = find_physics_path(
            physics_json_path
        )

        evidence_payload = await run_in_threadpool(
            run_full_pipeline,
            gene=gene,
            variant=variant,
            query=f"{gene} {variant}",
            confidence_threshold=0.7,
            physics_path=physics_path,
        )

        if isinstance(
            evidence_payload,
            dict,
        ):

            pipeline_status = (
                evidence_payload.get(
                    "status"
                )
            )

            confidence_matrix = (
                evidence_payload.get(
                    "confidence_matrix"
                )
            )

            payload_note = (
                evidence_payload.get(
                    "note"
                )
            )

        evidence = extract_evidence_from_payload(
            evidence_payload
        )

    except Exception as exc:

        warnings["literature_error"] = (
            "Literature evidence pipeline failed: "
            f"{str(exc)}"
        )

    # ========================================================================
    # 5. CLINICAL NARRATIVE
    # ========================================================================

    clinical_narrative = (
        extract_clinical_narrative(
            context_data
        )
    )

    if not clinical_narrative:

        clinical_narrative = (
            build_evidence_synthesis(
                gene=gene,
                variant=variant,
                status_value=pipeline_status,
                confidence_matrix=confidence_matrix,
                context_data=context_data,
                physics_data=physics_data,
                evidence=evidence,
            )
        )

    # If assemble_payload produced a specific VUS note,
    # preserve it as an additional warning/context signal,
    # but do not replace the synthesis.
    if payload_note and not clinical_narrative:

        clinical_narrative = payload_note

    # ========================================================================
    # 6. RESPONSE
    # ========================================================================

    return AnalyzeResponse(

        gene=gene,

        variant=variant,

        status=pipeline_status,

        confidence_matrix=confidence_matrix,

        context_data=context_data,

        physics_data=physics_data,

        pdb_content=pdb_content,

        evidence=evidence,

        clinical_narrative=clinical_narrative,

        warnings=warnings if warnings else None,
    )