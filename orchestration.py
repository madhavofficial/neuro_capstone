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
    logger.info(f"🔍 Phase 1: Fetching literature for {gene} {variant}...")
    
    try:
        from pipeline import fetch_literature_json
        corpus_path = fetch_literature_json(gene, variant)
        logger.info(f"✅ Phase 1 complete: {corpus_path}")
        return corpus_path
    except Exception as e:
        logger.error(f"❌ Phase 1 failed: {e}")
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
    logger.info(f"⚙️  Phase 2: Processing literature (chunking) for {gene} {variant}...")
    
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
            logger.info(f"✅ Phase 2 complete: {chunked_results}")
            return chunked_results
        except ImportError:
            # Fallback: assume corpus is already chunked or use alternative processor
            logger.warning("   - chunk_literature not found, assuming pre-chunked corpus")
            return corpus_path
    
    except Exception as e:
        logger.error(f"❌ Phase 2 failed: {e}")
        raise


# ==========================================
# PHASE 3: Vector Retrieval & Reranking
# ==========================================

def phase_3_vector_engine(gene: str, variant: str, query: str) -> List[Dict[str, Any]]:
    """
    Execute vector_engine module for retrieval and reranking.
    
    Args:
        gene: Gene symbol
        variant: Variant code
        query: Search query
    
    Returns:
        Top-K ranked results with rerank_score
    
    Raises:
        Exception: If retrieval fails
    """
    logger.info(f"🔎 Phase 3: Vector retrieval & reranking for query: '{query}'...")
    
    try:
        import vector_engine
        
        # Setup the pipeline (build embeddings and index if needed)
        logger.info("   - Setting up vector engine (embeddings & index)...")
        vector_engine.setup_pipeline(gene, variant)
        
        # Retrieve evidence
        log_msg = "   - Retrieving evidence with bi-encoder + cross-encoder reranking..."
        logger.info(log_msg)
        ranked_results = vector_engine.retrieve_evidence(gene, variant, query)
        
        logger.info(f"✅ Phase 3 complete: Retrieved {len(ranked_results)} ranked results")
        
        # Log sample scores for debugging
        if ranked_results:
            scores = [r.get("rerank_score", 0) for r in ranked_results]
            logger.debug(f"   - Rerank scores: {scores}")
        
        return ranked_results
    
    except Exception as e:
        logger.error(f"❌ Phase 3 failed: {e}")
        raise


# ==========================================
# PHASE 4: Assemble Payload
# ==========================================

def phase_4_assemble_payload(
    query: str,
    ranked_results: List[Dict[str, Any]],
    confidence_threshold: float = 0.7,
    output_path: str = "data/context_payload.json"
) -> Dict[str, Any]:
    """
    Execute assemble_payload module.
    
    Operations:
    - Threshold filtering (confidence gate)
    - Deduplication (max 1-2 chunks per PMID)
    - Deterministic sorting (by score, descending)
    - Structured JSON construction
    
    Args:
        query: Search query
        ranked_results: Top-K ranked results from Phase 3
        confidence_threshold: Minimum confidence score (default: 0.7)
    
    Returns:
        Structured payload dict
    
    Raises:
        Exception: If assembly fails
    """
    logger.info(f"📦 Phase 4: Assembling payload with threshold={confidence_threshold}...")
    
    try:
        import assemble_payload
        
        payload = assemble_payload.run(
            query=query,
            ranked_results=ranked_results,
            output_path=output_path
        )
        
        logger.info(f"✅ Phase 4 complete:")
        logger.info(f"   - Status: {payload['status']}")
        logger.info(f"   - Evidence items: {len(payload['evidence'])}")
        
        return payload
    
    except Exception as e:
        logger.error(f"❌ Phase 4 failed: {e}")
        raise


# ==========================================
# ORCHESTRATION
# ==========================================

def run_full_pipeline(
    gene: str,
    variant: str,
    query: str,
    confidence_threshold: float = 0.7,
    skip_phases: Optional[List[int]] = None
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
        query: Search query for evidence retrieval
        confidence_threshold: Minimum confidence score for filtering
        skip_phases: Optional list of phase numbers to skip (for testing)
    
    Returns:
        Final assembled payload with status, query, and evidence
    
    Example:
        payload = run_full_pipeline(
            gene="SNCA",
            variant="A53T",
            query="steric clash at position 53"
        )
    """
    skip_phases = skip_phases or []
    
    logger.info("=" * 70)
    logger.info("🚀 EVIDENCE PIPELINE ORCHESTRATION")
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
            logger.info("⏭️  Skipping Phase 1")
            corpus_path = f"data/literature/{gene}_{variant}_corpus.json"
        
        # Phase 2: Process Literature
        if 2 not in skip_phases:
            chunked_path = phase_2_process_literature(gene, variant, corpus_path)
        else:
            logger.info("⏭️  Skipping Phase 2")
            chunked_path = corpus_path
        
        # Phase 3: Vector Engine
        if 3 not in skip_phases:
            ranked_results = phase_3_vector_engine(gene, variant, query)
        else:
            logger.info("⏭️  Skipping Phase 3")
            ranked_results = []
        
        # Phase 4: Assemble Payload
        if 4 not in skip_phases:
            payload = phase_4_assemble_payload(query, ranked_results, confidence_threshold)
        else:
            logger.info("⏭️  Skipping Phase 4")
            payload = {
                "status": "skipped",
                "query": query,
                "evidence": []
            }
        
        logger.info("=" * 70)
        logger.info("✅ PIPELINE COMPLETE")
        logger.info("=" * 70)
        
        return payload
    
    except Exception as e:
        logger.error("=" * 70)
        logger.error("❌ PIPELINE FAILED")
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
        print("📤 FINAL PAYLOAD")
        print("=" * 70)
        print(json.dumps(payload, indent=2))
        
        return 0
    
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
