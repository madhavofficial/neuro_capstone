"""
Main Application: Evidence Retrieval Pipeline

This module demonstrates how to use the orchestration controller to run
the complete evidence retrieval pipeline:

  fetch_literature → process_literature → vector_engine → assemble_payload

The pipeline is designed to be:
 Modular: Each phase can be tested independently
 Decoupled: Phases don't directly depend on each other's internals
 Configurable: Threshold, max chunks, and other parameters are adjustable
 Structured: Output is machine-readable JSON for downstream consumption
"""

import json
import argparse
from typing import Optional
from orchestration import run_full_pipeline


def print_payload_summary(payload: dict) -> None:
    """Pretty-print a summary of the assembled payload."""
    print("\n" + "=" * 70)
    print(">> EVIDENCE PAYLOAD SUMMARY")
    print("=" * 70)
    print(f"Status: {payload['status']}")
    print(f"Query:  {payload['query']}")
    print(f"Evidence Items: {len(payload['evidence'])}")
    
    if payload['evidence']:
        print("\nTop Evidence:")
        for i, item in enumerate(payload['evidence'], 1):
            print(f"\n  [{i}] PMID: {item['pmid']}")
            print(f"      Score: {item['score']:.3f}")
            print(f"      Title: {item['title'][:60]}...")
            print(f"      Text: {item['text'][:100]}...")
    
    print("=" * 70 + "\n")


def run_example(
    gene: str = "SNCA",
    variant: str = "A53T",
    query: str = "steric clash at position 53 alpha-synuclein aggregation",
    threshold: float = 0.7
) -> dict:
    """
    Run a complete example of the evidence pipeline.
    
    Args:
        gene: Gene symbol
        variant: Variant code
        query: Search query
        threshold: Confidence threshold
    
    Returns:
        Assembled payload dict
    """
    print(f"\n Running Evidence Pipeline for {gene} {variant}")
    print(f"   Query: {query}")
    print(f"   Threshold: {threshold}")
    
    try:
        payload = run_full_pipeline(
            gene=gene,
            variant=variant,
            query=query,
            confidence_threshold=threshold
        )
        
        print_payload_summary(payload)
        
        # Save to file
        output_file = "data/context_payload.json"
        with open(output_file, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"[OK] Payload saved to {output_file}")
        
        return payload
    
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        raise


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Evidence Retrieval Pipeline"
    )
    parser.add_argument(
        "--gene",
        default="SNCA",
        help="Gene symbol (default: SNCA)"
    )
    parser.add_argument(
        "--variant",
        default="A53T",
        help="Variant code (default: A53T)"
    )
    parser.add_argument(
        "--query",
        required=False,
        help="Search query for evidence retrieval"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.7,
        help="Confidence threshold (default: 0.7)"
    )
    parser.add_argument(
        "--example",
        action="store_true",
        help="Run with default example values"
    )
    
    args = parser.parse_args()
    
    if args.example:
        run_example()
    else:
        if not args.query:
            parser.error("--query is required unless using --example")
        
        run_example(
            gene=args.gene,
            variant=args.variant,
            query=args.query,
            threshold=args.threshold
        )


if __name__ == "__main__":
    main()
