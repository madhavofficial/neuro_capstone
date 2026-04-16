"""
Assemble Payload Module

Processes ranked evidence chunks from vector_engine and constructs
a structured, machine-readable JSON payload for LLM consumption.

Key responsibilities:
- Threshold filtering (confidence gate)
- Deduplication (max 1-2 chunks per PMID)
- Deterministic sorting (by score, descending)
- Structured JSON output
"""

import json
import os
from typing import List, Dict, Any, Optional


# Configuration
CONFIDENCE_THRESHOLD = 0.7
MAX_CHUNKS_PER_PMID = 2
OUTPUT_PATH = "data/context_payload.json"


def filter_by_threshold(results: List[Dict[str, Any]], threshold: float = CONFIDENCE_THRESHOLD) -> tuple[List[Dict[str, Any]], bool]:
    """
    Apply confidence threshold filtering.
    
    Args:
        results: List of ranked results with rerank_score
        threshold: Minimum confidence score (default: 0.7)
    
    Returns:
        Tuple of (filtered_results, low_confidence_flag)
        - If any result passes threshold, returns those results
        - If no results pass, returns best available result with low_confidence=True
    """
    if not results:
        return [], True
    
    passed = [r for r in results if r.get("rerank_score", 0) >= threshold]
    
    if passed:
        return passed, False
    
    # Fallback: return the single best result but flag as LOW_CONFIDENCE
    return [results[0]], True


def deduplicate_by_pmid(results: List[Dict[str, Any]], max_per_pmid: int = MAX_CHUNKS_PER_PMID) -> List[Dict[str, Any]]:
    """
    Ensure evidence diversity by limiting chunks per PMID.
    
    Args:
        results: Filtered and sorted results
        max_per_pmid: Maximum chunks allowed per unique PMID
    
    Returns:
        Deduplicated list maintaining order and score
    """
    pmid_counts = {}
    deduplicated = []
    
    for result in results:
        pmid = result.get("pmid")
        
        # Initialize count for this PMID if not seen
        if pmid not in pmid_counts:
            pmid_counts[pmid] = 0
        
        # Only include if we haven't exceeded max for this PMID
        if pmid_counts[pmid] < max_per_pmid:
            deduplicated.append(result)
            pmid_counts[pmid] += 1
    
    return deduplicated


def sort_by_score(results: List[Dict[str, Any]], descending: bool = True) -> List[Dict[str, Any]]:
    """
    Deterministically sort by rerank_score.
    
    Args:
        results: List of results to sort
        descending: If True, highest scores first (default: True)
    
    Returns:
        Sorted list
    """
    return sorted(
        results,
        key=lambda x: x.get("rerank_score", 0),
        reverse=descending
    )


def construct_evidence_item(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and format evidence from a ranked result.
    
    Args:
        result: Ranked result with chunk, pmid, title, rerank_score
    
    Returns:
        Structured evidence item
    """
    return {
        "text": result.get("chunk", ""),
        "pmid": result.get("pmid", ""),
        "title": result.get("title", ""),
        "score": result.get("rerank_score", 0.0)
    }


def assemble_payload(
    query: str,
    ranked_results: List[Dict[str, Any]],
    confidence_threshold: float = CONFIDENCE_THRESHOLD
) -> Dict[str, Any]:
    """
    Orchestrate the assembly of a structured JSON payload.
    
    Process:
    1. Threshold filtering (with fallback on low confidence)
    2. Deduplication (max 1-2 chunks per PMID)
    3. Deterministic sorting (by score, descending)
    4. Structured construction
    
    Args:
        query: Original search query
        ranked_results: Top-K ranked chunks from vector_engine with rerank_score
        confidence_threshold: Minimum score threshold (default: 0.7)
    
    Returns:
        Structured payload dict with keys: status, query, evidence
    """
    # Step 1: Filter by threshold
    filtered_results, low_confidence = filter_by_threshold(
        ranked_results,
        threshold=confidence_threshold
    )
    
    # Step 2: Deduplicate
    deduplicated = deduplicate_by_pmid(filtered_results)
    
    # Step 3: Sort deterministically
    sorted_results = sort_by_score(deduplicated, descending=True)
    
    # Step 4: Construct evidence array
    evidence = [construct_evidence_item(result) for result in sorted_results]
    
    # Step 5: Build final payload
    payload = {
        "status": "LOW_CONFIDENCE" if low_confidence else "success",
        "query": query,
        "evidence": evidence
    }
    
    return payload


def save_payload(payload: Dict[str, Any], output_path: str = OUTPUT_PATH) -> str:
    """
    Save structured payload to JSON file.
    
    Args:
        payload: Structured payload dict
        output_path: Where to save (default: data/context_payload.json)
    
    Returns:
        Path where payload was saved
    """
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    
    return output_path


def run(query: str, ranked_results: List[Dict[str, Any]], output_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Complete pipeline: assemble and save payload.
    
    Args:
        query: Search query
        ranked_results: Top-K ranked results from vector_engine
        output_path: Optional custom output path (default: data/context_payload.json)
    
    Returns:
        The assembled payload dict
    """
    payload = assemble_payload(query, ranked_results)
    
    final_path = output_path or OUTPUT_PATH
    saved_path = save_payload(payload, final_path)
    
    print(f"✅ Payload assembled and saved: {saved_path}")
    print(f"   - Status: {payload['status']}")
    print(f"   - Evidence items: {len(payload['evidence'])}")
    
    return payload


if __name__ == "__main__":
    import sys
    
    # Example usage for testing
    if len(sys.argv) > 1:
        query = sys.argv[1]
        print(f"Running assemble_payload with query: {query}")
    else:
        print("Usage: python assemble_payload.py '<query>'")
        print("Note: This is typically called from the orchestration controller")
