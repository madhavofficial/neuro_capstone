"""
Master Orchestration Controller

Executes the evidence pipeline in strict sequence:
  1. fetch_literature   → Retrieves papers from PubMed/EuroPePMC
  2. process_literature → Chunks and processes text
  3. vector_engine      → Encodes and retrieves top-K candidates with reranking
  4. assemble_payload   → Filters, deduplicates, and assembles structured output

Key Design Principles:
  - Decoupled execution: modules can be tested independently
  - Strict sequencing: ensures data flows through the pipeline correctly
  - Error handling: graceful failures with informative messages
"""

import os
import sys
import json
import argparse
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ==========================================
# PHASE 1: Fetch Literature
# ==========================================

def phase_1_fetch_literature(gene: str, variant: str) -> str:
    """
    Execute fetch_literature module.
    
    Args:
        gene: Gene symbol (e.g., "SNCA")
        variant: Variant code (e.g., "A53T")
    
    Returns:
        Path to fetched corpus JSON
    
    Raises:
        Exception: If literature fetch fails
    """
    logger.info(f">> Phase 1: Fetching literature for {gene} {variant}...")
    
    try:
        from pipeline import fetch_literature_json
        corpus_path = fetch_literature_json(gene, variant)
        logger.info(f"[OK] Phase 1 complete: {corpus_path}")
        return corpus_path
    except Exception as e:
        logger.error(f"[ERROR] Phase 1 failed: {e}")
        raise


# ==========================================
# PHASE 2: Process Literature
# ==========================================

def phase_2_process_literature(gene: str, variant: str, corpus_path: str) -> str:
    """
    Execute process_literature module (chunking).
    
    Args:
        gene: Gene symbol
        variant: Variant code
        corpus_path: Path to raw corpus JSON
    
    Returns:
        Path to processed (chunked) corpus
    
    Raises:
        Exception: If processing fails
    """
    logger.info(f"️  Phase 2: Processing literature (chunking) for {gene} {variant}...")
    
    try:
        # Load raw corpus
        if not os.path.exists(corpus_path):
            raise FileNotFoundError(f"Corpus not found: {corpus_path}")
        
        with open(corpus_path, "r", encoding="utf-8") as f:
            corpus = json.load(f)
        
        logger.info(f"   - Loaded {len(corpus) if isinstance(corpus, list) else 1} papers")
        
        # Import processing function
        try:
            from pipeline import chunk_literature
            chunked_results = chunk_literature(corpus, gene, variant)
            logger.info(f"[OK] Phase 2 complete: {chunked_results}")
            return chunked_results
        except ImportError:
            # Fallback: assume corpus is already chunked or use alternative processor
            logger.warning("   - chunk_literature not found, assuming pre-chunked corpus")
            return corpus_path
    
    except Exception as e:
        logger.error(f"[ERROR] Phase 2 failed: {e}")
        raise


# ==========================================
# PHASE 3: Vector Retrieval & Reranking
# ==========================================

def phase_3_vector_engine(
    gene: str,
    variant: str,
    query: str,
    keyword_boost_hints: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Execute vector_engine module for retrieval and reranking.

    Args:
        gene: Gene symbol
        variant: Variant code
        query: Search query
        keyword_boost_hints: Variant alias strings for the keyword safety-net
            score boost inside vector_engine.rerank().

    Returns:
        Top-K ranked results with rerank_score

    Raises:
        Exception: If retrieval fails
    """
    logger.info(f">> Phase 3: Vector retrieval & reranking for query: '{query}'...")
    if keyword_boost_hints:
        logger.info(f"   - Keyword boost hints: {keyword_boost_hints}")

    try:
        import vector_engine

        # Setup the pipeline (build embeddings and index if needed)
        logger.info("   - Setting up vector engine (embeddings & index)...")
        vector_engine.setup_pipeline(gene, variant)

        # Retrieve evidence (with optional keyword safety-net hints)
        log_msg = "   - Retrieving evidence with bi-encoder + cross-encoder reranking..."
        logger.info(log_msg)
        ranked_results = vector_engine.retrieve_evidence(
            gene, variant, query, keyword_boost_hints=keyword_boost_hints
        )

        logger.info(f"[OK] Phase 3 complete: Retrieved {len(ranked_results)} ranked results")

        # Log sample scores for debugging
        if ranked_results:
            scores = [r.get("rerank_score", 0) for r in ranked_results]
            logger.debug(f"   - Rerank scores: {scores}")

        return ranked_results

    except Exception as e:
        logger.error(f"[ERROR] Phase 3 failed: {e}")
        raise


# ==========================================
# PHASE 4: Assemble Payload
# ==========================================

def phase_4_assemble_payload(
    query: str,
    ranked_results: List[Dict[str, Any]],
    confidence_threshold: float = 0.7,
    output_path: str = "data/context_payload.json",
    physics_vector: Optional[Dict[str, Any]] = None,
    rag_status: str = "NULL_RESULTS",
    clinical_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute assemble_payload module.

    Operations:
    - Threshold filtering (confidence gate)
    - Deduplication (max 1-2 chunks per PMID)
    - Deterministic sorting (by score, descending)
    - Modular confidence_matrix construction
    - Global status derivation (including STRUCTURAL_DISCOVERY_VUS logic gate)

    Args:
        query: Search query
        ranked_results: Top-K ranked results from Phase 3
        confidence_threshold: Minimum confidence score (default: 0.7)
        output_path: Where to write the payload JSON
        physics_vector: Optional physics dict for VUS promotion.
        rag_status: Retrieval outcome hint (SUCCESS / NULL_RESULTS / TIMEOUT_ERROR).
        clinical_context: Optional dict from fetch_context for clinical_context cell.

    Returns:
        Structured payload dict

    Raises:
        Exception: If assembly fails
    """
    logger.info(f">> Phase 4: Assembling payload (threshold={confidence_threshold}, rag={rag_status})...")

    try:
        import assemble_payload

        payload = assemble_payload.run(
            query=query,
            ranked_results=ranked_results,
            output_path=output_path,
            physics_vector=physics_vector,
            rag_status=rag_status,
            clinical_context=clinical_context,
        )

        status = payload["status"]
        matrix = payload.get("confidence_matrix", {})
        logger.info(f"[OK] Phase 4 complete:")
        logger.info(f"   - Status:         {status}")
        logger.info(f"   - Evidence items: {len(payload['evidence'])}")
        logger.info(f"   - Physics engine: {matrix.get('physics_engine', '?')}")
        logger.info(f"   - RAG:            {matrix.get('literature_rag', '?')}")
        logger.info(f"   - Clinical:       {matrix.get('clinical_context', '?')}")
        if status in {"STRUCTURAL_DISCOVERY_VUS", "PREDICTED_PATHOGENIC_VUS"}:
            n = payload.get("physics_violations", {}).get("count", 0)
            logger.info(f"   - Physics violations (severe): {n}")

        return payload

    except Exception as e:
        logger.error(f"[ERROR] Phase 4 failed: {e}")
        raise


# ==========================================
# ORCHESTRATION
# ==========================================

def run_full_pipeline(
    gene: str,
    variant: str,
    query: str,
    confidence_threshold: float = 0.7,
    skip_phases: Optional[List[int]] = None,
    physics_path: Optional[str] = None,
    mechanism_tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Execute the complete evidence pipeline in strict sequence.

    Pipeline Phases:
    1. fetch_literature    - Retrieve papers from PubMed/EuroPePMC
    2. process_literature  - Chunk and process text
    3. vector_engine       - Bi-encoder retrieval + cross-encoder reranking
    4. assemble_payload    - Filter, deduplicate, assemble final output

    Args:
        gene: Gene symbol (e.g., "SNCA")
        variant: Variant code (e.g., "A53T")
        query: Search query for evidence retrieval (overridden by nlp_formation
               when physics_path is provided)
        confidence_threshold: Minimum confidence score for filtering
        skip_phases: Optional list of phase numbers to skip (for testing)
        physics_path: Optional path to physics JSON. When provided, nlp_formation
                      is run internally to build the hybrid query and derive
                      keyword_boost_hints for the safety-net reranker.
        mechanism_tags: Optional list of qualitative mechanism tags from
                        analyze_structure to inject into the physics dict before
                        query generation (e.g. ['alpha-helix disruption']).

    Returns:
        Final assembled payload with status, query, and evidence

    Example:
        payload = run_full_pipeline(
            gene="SNCA",
            variant="A53T",
            query="steric clash at position 53",
            physics_path="data/analysis/SNCA_A53T_physics.json",
        )
    """
    skip_phases = skip_phases or []
    keyword_boost_hints: List[str] = []
    physics_dict: Optional[Dict[str, Any]] = None  # kept in scope for Phase 4 VUS promotion

    # ── Physics-driven query override (Hybrid Query Builder) ──────────────────
    # If a physics_path is given, regenerate the NLP query from biophysics data
    # and capture the keyword_boost_hints for the safety-net reranker.
    if physics_path and os.path.exists(physics_path):
        try:
            with open(physics_path, "r", encoding="utf-8") as f:
                physics_dict = json.load(f)

            # Inject qualitative mechanism_tags from orchestration layer
            if mechanism_tags:
                physics_dict["mechanism_tags"] = mechanism_tags

            from nlp_formation import create_nlp_query
            raw_query, keyword_boost_hints = create_nlp_query(physics_dict)

            # Prepend gene symbol as the mutation signature anchor
            if not raw_query.startswith(gene):
                raw_query = f"{gene} {raw_query}"
            query = raw_query
            logger.info(f">> Physics-driven query built: '{query[:120]}...'")
            logger.info(f">> Keyword boost hints: {keyword_boost_hints}")
        except Exception as e:
            logger.warning(f"[WARN]  Physics-driven query failed, using provided query: {e}")

    logger.info("=" * 70)
    logger.info(" EVIDENCE PIPELINE ORCHESTRATION")
    logger.info("=" * 70)
    logger.info(f"Gene: {gene}, Variant: {variant}")
    logger.info(f"Query: {query}")
    logger.info(f"Confidence Threshold: {confidence_threshold}")
    logger.info("=" * 70)

    try:
        # Phase 1: Fetch Literature
        if 1 not in skip_phases:
            corpus_path = phase_1_fetch_literature(gene, variant)
        else:
            logger.info("[SKIP]  Skipping Phase 1")
            corpus_path = f"data/literature/{gene}_{variant}_corpus.json"

        # Phase 2: Process Literature
        if 2 not in skip_phases:
            chunked_path = phase_2_process_literature(gene, variant, corpus_path)
        else:
            logger.info("[SKIP]  Skipping Phase 2")
            chunked_path = corpus_path

        # Phase 3: Vector Engine (with keyword safety-net hints)
        _rag_status = "NULL_RESULTS"   # updated below based on retrieval outcome
        if 3 not in skip_phases:
            try:
                ranked_results = phase_3_vector_engine(
                    gene, variant, query, keyword_boost_hints=keyword_boost_hints
                )
                _rag_status = "SUCCESS" if ranked_results else "NULL_RESULTS"
            except Exception as e3:
                # Distinguish empty-corpus (timeout) from other errors
                err_msg = str(e3).lower()
                _rag_status = "TIMEOUT_ERROR" if "empty" in err_msg or "timeout" in err_msg else "NULL_RESULTS"
                logger.warning(f"[WARN]  Phase 3 retrieval issue ({_rag_status}): {e3}")
                ranked_results = []
        else:
            logger.info("[SKIP]  Skipping Phase 3")
            ranked_results = []

        # Phase 4: Assemble Payload (physics_vector + rag_status enable confidence matrix)
        if 4 not in skip_phases:
            payload = phase_4_assemble_payload(
                query, ranked_results, confidence_threshold,
                physics_vector=physics_dict,
                rag_status=_rag_status,
                clinical_context=None,  # context not held here; pipeline.py passes it
            )
        else:
            logger.info("[SKIP]  Skipping Phase 4")
            payload = {
                "status": "skipped",
                "query": query,
                "evidence": []
            }

        logger.info("=" * 70)
        logger.info("[OK] PIPELINE COMPLETE")
        logger.info("=" * 70)

        return payload

    except Exception as e:
        logger.error("=" * 70)
        logger.error("[ERROR] PIPELINE FAILED")
        logger.error("=" * 70)
        raise


# ==========================================
# CLI INTERFACE
# ==========================================

def main():
    """Command-line interface for the orchestration controller."""
    parser = argparse.ArgumentParser(
        description="Execute the evidence retrieval pipeline"
    )
    parser.add_argument(
        "gene",
        help="Gene symbol (e.g., SNCA)"
    )
    parser.add_argument(
        "variant",
        help="Variant code (e.g., A53T)"
    )
    parser.add_argument(
        "--query",
        required=True,
        help="Search query for evidence retrieval"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.7,
        help="Confidence threshold for filtering (default: 0.7)"
    )
    parser.add_argument(
        "--skip-phase",
        type=int,
        action="append",
        dest="skip_phases",
        help="Skip a pipeline phase (1-4). Can be used multiple times."
    )
    
    args = parser.parse_args()
    
    try:
        payload = run_full_pipeline(
            gene=args.gene,
            variant=args.variant,
            query=args.query,
            confidence_threshold=args.threshold,
            skip_phases=args.skip_phases
        )
        
        print("\n" + "=" * 70)
        print(" FINAL PAYLOAD")
        print("=" * 70)
        print(json.dumps(payload, indent=2))
        
        return 0
    
    except Exception as e:
        print(f"\n[ERROR] Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
