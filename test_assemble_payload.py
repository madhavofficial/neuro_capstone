"""
Unit Tests for Payload Assembly

Tests the core functionality of assemble_payload.py independently
to ensure each operation works correctly.
"""

import json
import tempfile
import os
from assemble_payload import (
    filter_by_threshold,
    deduplicate_by_pmid,
    sort_by_score,
    construct_evidence_item,
    assemble_payload,
    save_payload
)


def test_threshold_filtering():
    """Test confidence threshold filtering."""
    results = [
        {"chunk": "text1", "pmid": "111", "title": "t1", "rerank_score": 0.9},
        {"chunk": "text2", "pmid": "222", "title": "t2", "rerank_score": 0.65},
        {"chunk": "text3", "pmid": "333", "title": "t3", "rerank_score": 0.8},
    ]
    
    # Test: Pass threshold
    filtered, low_conf = filter_by_threshold(results, threshold=0.7)
    assert len(filtered) == 2, "Should have 2 results above 0.7"
    assert low_conf is False, "Should not flag as low confidence"
    
    # Test: Fail threshold (fallback)
    filtered, low_conf = filter_by_threshold(results, threshold=0.95)
    assert len(filtered) == 1, "Should fallback to best result"
    assert low_conf is True, "Should flag as low confidence"
    assert filtered[0]["rerank_score"] == 0.9, "Should return best result"
    
    print("[OK] test_threshold_filtering passed")


def test_deduplication():
    """Test PMID deduplication."""
    results = [
        {"chunk": "text1", "pmid": "111", "title": "t1", "rerank_score": 0.9},
        {"chunk": "text2", "pmid": "111", "title": "t1", "rerank_score": 0.85},
        {"chunk": "text3", "pmid": "222", "title": "t2", "rerank_score": 0.8},
        {"chunk": "text4", "pmid": "111", "title": "t1", "rerank_score": 0.75},
        {"chunk": "text5", "pmid": "333", "title": "t3", "rerank_score": 0.7},
    ]
    
    # Test: Max 2 per PMID
    deduped = deduplicate_by_pmid(results, max_per_pmid=2)
    assert len(deduped) == 4, "Should have 4 items (2 from PMID 111, 1 each from 222, 333)"
    
    # Count per PMID
    pmid_111_count = sum(1 for r in deduped if r["pmid"] == "111")
    pmid_222_count = sum(1 for r in deduped if r["pmid"] == "222")
    pmid_333_count = sum(1 for r in deduped if r["pmid"] == "333")
    
    assert pmid_111_count == 2, "PMID 111 should have max 2"
    assert pmid_222_count == 1, "PMID 222 should have 1"
    assert pmid_333_count == 1, "PMID 333 should have 1"
    
    # Test: Max 1 per PMID
    deduped = deduplicate_by_pmid(results, max_per_pmid=1)
    assert len(deduped) == 3, "Should have 3 items (1 from each PMID)"
    
    print("[OK] test_deduplication passed")


def test_deterministic_sorting():
    """Test scoring-based sorting."""
    results = [
        {"chunk": "text1", "pmid": "111", "title": "t1", "rerank_score": 0.7},
        {"chunk": "text2", "pmid": "222", "title": "t2", "rerank_score": 0.95},
        {"chunk": "text3", "pmid": "333", "title": "t3", "rerank_score": 0.8},
    ]
    
    # Test: Descending (highest first)
    sorted_desc = sort_by_score(results, descending=True)
    scores = [r["rerank_score"] for r in sorted_desc]
    assert scores == [0.95, 0.8, 0.7], "Should be sorted descending"
    
    # Test: Ascending (lowest first)
    sorted_asc = sort_by_score(results, descending=False)
    scores = [r["rerank_score"] for r in sorted_asc]
    assert scores == [0.7, 0.8, 0.95], "Should be sorted ascending"
    
    print("[OK] test_deterministic_sorting passed")


def test_evidence_construction():
    """Test evidence item construction."""
    result = {
        "chunk": "A53T causes steric clash",
        "pmid": "15331649",
        "title": "Effect of A53T on alpha-synuclein",
        "rerank_score": 0.87
    }
    
    item = construct_evidence_item(result)
    
    assert item["text"] == "A53T causes steric clash"
    assert item["pmid"] == "15331649"
    assert item["title"] == "Effect of A53T on alpha-synuclein"
    assert item["score"] == 0.87
    
    print("[OK] test_evidence_construction passed")


def test_full_assembly():
    """Test complete payload assembly."""
    query = "steric clash at position 53"
    results = [
        {"chunk": "text1", "pmid": "111", "title": "t1", "rerank_score": 0.9},
        {"chunk": "text2", "pmid": "222", "title": "t2", "rerank_score": 0.85},
        {"chunk": "text3", "pmid": "111", "title": "t1", "rerank_score": 0.8},
        {"chunk": "text4", "pmid": "333", "title": "t3", "rerank_score": 0.65},
    ]
    
    payload = assemble_payload(query, results, confidence_threshold=0.7)
    
    # Check structure
    assert "status" in payload
    assert "query" in payload
    assert "evidence" in payload
    
    # Check status
    assert payload["status"] == "success", "Should pass threshold"
    
    # Check query
    assert payload["query"] == query
    
    # Check evidence
    assert len(payload["evidence"]) == 3, "Should have 3 items (111x2, 222, 333 below threshold=0.65 fallback)"
    
    # Check sorting (highest score first)
    scores = [e["score"] for e in payload["evidence"]]
    assert scores == sorted(scores, reverse=True), "Should be sorted descending"
    
    print("[OK] test_full_assembly passed")


def test_low_confidence_status():
    """Test LOW_CONFIDENCE status flag."""
    query = "obscure query"
    results = [
        {"chunk": "text1", "pmid": "111", "title": "t1", "rerank_score": 0.55},
    ]
    
    payload = assemble_payload(query, results, confidence_threshold=0.7)
    
    assert payload["status"] == "LOW_CONFIDENCE", "Should flag low confidence"
    assert len(payload["evidence"]) == 1, "Should still return best result"
    
    print("[OK] test_low_confidence_status passed")


def test_save_payload():
    """Test payload file saving."""
    payload = {
        "status": "success",
        "query": "test query",
        "evidence": [
            {"text": "text", "pmid": "123", "title": "title", "score": 0.9}
        ]
    }
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "test_payload.json")
        saved_path = save_payload(payload, output_path)
        
        assert saved_path == output_path
        assert os.path.exists(saved_path), "File should exist"
        
        # Verify content
        with open(saved_path) as f:
            loaded = json.load(f)
        
        assert loaded == payload, "Loaded payload should match original"
    
    print("[OK] test_save_payload passed")


def run_all_tests():
    """Run all unit tests."""
    print("\n" + "=" * 70)
    print(" RUNNING UNIT TESTS FOR ASSEMBLE_PAYLOAD")
    print("=" * 70 + "\n")
    
    test_threshold_filtering()
    test_deduplication()
    test_deterministic_sorting()
    test_evidence_construction()
    test_full_assembly()
    test_low_confidence_status()
    test_save_payload()
    
    print("\n" + "=" * 70)
    print("[OK] ALL TESTS PASSED")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_all_tests()
