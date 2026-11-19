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
    save_payload,
    run,
    build_confidence_matrix,
    build_site_description,
    derive_global_status,
    evaluate_physics_severity,
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
    assert item["score_type"] == "raw_cross_encoder_score"
    
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
    assert payload["status"] == "SUCCESS", "Should pass threshold"
    
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


def test_run_forwards_confidence_threshold():
    """The file-writing wrapper must honor a caller-provided threshold."""
    results = [
        {"chunk": "text", "pmid": "111", "title": "t1", "rerank_score": 0.8},
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "payload.json")
        payload = run(
            "query",
            results,
            confidence_threshold=0.85,
            output_path=output_path,
        )

    assert payload["status"] == "LOW_CONFIDENCE"
    print("[OK] test_run_forwards_confidence_threshold passed")


def test_confidence_matrix_distinguishes_evidence_scope():
    """Gene-level coverage must not be reported as exact-variant evidence."""
    gene_level = {
        "clinvar": {
            "scope": "gene_level",
            "variant_match": False,
            "clinical_significance": "Gene has pathogenic variants in ClinVar",
        }
    }
    matrix = build_confidence_matrix(
        {"deltas": {"delta_volume": 54}},
        "SUCCESS",
        gene_level,
    )
    assert matrix["clinical_context"] == "PARTIAL"
    assert matrix["clinical_context_scope"] == "GENE_LEVEL"
    assert matrix["physics_engine"] == "HEURISTIC"
    assert matrix["physics_evidence_scope"] == "SITE_PROPERTY_HEURISTIC"

    exact = {
        "clinvar": {
            "scope": "exact_variant",
            "variant_match": True,
            "clinical_significance": "Pathogenic",
        }
    }
    exact_matrix = build_confidence_matrix(None, "NULL_RESULTS", exact)
    assert exact_matrix["clinical_context"] == "HIGH"
    assert exact_matrix["clinical_context_scope"] == "EXACT_VARIANT"

    print("[OK] test_confidence_matrix_distinguishes_evidence_scope passed")


def _site_physics(**overrides):
    """A physics dict with wild-type context, table deltas, and a null mutant view."""
    physics = {
        "variant": "A53T",
        "structural_context_wt": {
            "exposure": "Buried",
            "sasa": 8.4,
            "secondary_structure": "Alpha Helix",
            "plddt_confidence": 91.2,
        },
        "deltas": {
            "delta_volume": 27.5,
            "delta_hydrophobicity": -1.4,
            "delta_charge": 1.0,
        },
        "delta_aggregation": 0.35,
        "comparison_view": {
            "sasa": {"wt": 8.4, "mut": None, "delta": None},
            "plddt_confidence": {"wt": 91.2, "mut": None, "delta": None},
        },
        "stability_audit": {
            "salt_bridges_lost": 2,
            "h_bonds_lost_est": 1,
        },
        "interface_contacts_lost": 3,
    }
    physics.update(overrides)
    return physics


def _labeled_values(description):
    """Every {value, label} object stored on a site description."""
    return {
        key: item
        for key, item in description.items()
        if isinstance(item, dict) and "label" in item
    }


def test_site_description_labels_present_values():
    """Wild-type context, table deltas, and aggregation are labeled, with a disclaimer."""
    evidence = [
        {"chunk": "text", "pmid": "111", "title": "t1", "rerank_score": 0.9},
    ]
    payload = assemble_payload(
        "A53T",
        evidence,
        physics_vector=_site_physics(),
        rag_status="SUCCESS",
    )

    assert payload["status"] == "SUCCESS"
    site = payload["site_description"]
    assert "not a measured folding effect" in site["note"]
    assert "not proof of pathogenicity" in site["note"]

    labeled = _labeled_values(site)
    assert labeled["exposure"] == {"value": "Buried", "label": "wild-type measurement"}
    assert labeled["sasa"] == {"value": 8.4, "label": "wild-type measurement"}
    assert labeled["secondary_structure"] == {
        "value": "Alpha Helix",
        "label": "wild-type measurement",
    }
    assert labeled["plddt_confidence"] == {"value": 91.2, "label": "wild-type measurement"}
    assert labeled["delta_volume"] == {"value": 27.5, "label": "amino-acid table lookup"}
    assert labeled["delta_hydrophobicity"] == {
        "value": -1.4,
        "label": "amino-acid table lookup",
    }
    assert labeled["delta_charge"] == {"value": 1.0, "label": "amino-acid table lookup"}
    assert labeled["delta_aggregation"] == {"value": 0.35, "label": "amino-acid table lookup"}

    rendered = json.dumps(site)
    assert "salt_bridge" not in rendered
    assert "h_bond" not in rendered
    assert "interface" not in rendered

    print("[OK] test_site_description_labels_present_values passed")


def test_null_mutant_fields_are_not_described_as_changes():
    """A null aggregation delta and null mutant SASA / pLDDT are omitted."""
    physics = _site_physics(delta_aggregation=None)
    payload = assemble_payload("A53T", [], physics_vector=physics)
    site = payload["site_description"]

    assert "delta_aggregation" not in site
    rendered = json.dumps(site)
    assert "delta_aggregation" not in rendered
    assert '"mut"' not in rendered
    assert "null" not in rendered
    assert "structural change" not in rendered.lower()
    assert site["sasa"] == {"value": 8.4, "label": "wild-type measurement"}
    assert site["plddt_confidence"]["value"] == 91.2
    assert "delta_sasa" not in site
    assert "delta_plddt_confidence" not in site

    missing = _site_physics()
    del missing["delta_aggregation"]
    omitted = build_site_description(missing)
    assert "delta_aggregation" not in omitted

    print("[OK] test_null_mutant_fields_are_not_described_as_changes passed")


def test_table_deltas_do_not_change_severity_or_status():
    """A large volume or hydrophobicity delta is not severe and does not change status."""
    large_deltas = {
        "delta_volume": 120.0,
        "delta_hydrophobicity": -6.0,
        "delta_charge": 0.0,
    }
    zero_deltas = {
        "delta_volume": 0.0,
        "delta_hydrophobicity": 0.0,
        "delta_charge": 0.0,
    }
    large = _site_physics(deltas=large_deltas, delta_aggregation=None)
    zero = _site_physics(deltas=zero_deltas, delta_aggregation=None)

    severe, violations, count = evaluate_physics_severity(large)
    assert severe is False
    assert violations == []
    assert count == 0

    # No literature and no clinical record: this is the only gate that reads
    # physics severity. A table delta must not promote the case.
    large_payload = assemble_payload(
        "A53T", [], physics_vector=large, rag_status="NULL_RESULTS",
    )
    zero_payload = assemble_payload(
        "A53T", [], physics_vector=zero, rag_status="NULL_RESULTS",
    )
    assert large_payload["status"] == zero_payload["status"]
    assert large_payload["status"] == "LOW_CONFIDENCE"

    large_status = derive_global_status(
        large_payload["confidence_matrix"],
        has_evidence=False,
        low_confidence=True,
        physics_vector=large,
    )
    zero_status = derive_global_status(
        zero_payload["confidence_matrix"],
        has_evidence=False,
        low_confidence=True,
        physics_vector=zero,
    )
    assert large_status == zero_status

    print("[OK] test_table_deltas_do_not_change_severity_or_status passed")


def test_payload_without_physics_omits_site_description():
    """Literature-only assembly has no physics dict and no site_description key."""
    evidence = [
        {"chunk": "text", "pmid": "111", "title": "t1", "rerank_score": 0.9},
    ]
    payload = assemble_payload("A53T", evidence, rag_status="SUCCESS")
    assert "site_description" not in payload
    assert payload["status"] == "SUCCESS"

    print("[OK] test_payload_without_physics_omits_site_description passed")


def test_save_payload():
    """Test payload file saving."""
    payload = {
        "status": "SUCCESS",
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
    test_run_forwards_confidence_threshold()
    test_confidence_matrix_distinguishes_evidence_scope()
    test_site_description_labels_present_values()
    test_null_mutant_fields_are_not_described_as_changes()
    test_table_deltas_do_not_change_severity_or_status()
    test_payload_without_physics_omits_site_description()
    test_save_payload()
    
    print("\n" + "=" * 70)
    print("[OK] ALL TESTS PASSED")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_all_tests()
