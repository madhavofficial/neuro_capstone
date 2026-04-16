# Evidence Pipeline Implementation Guide

## Overview

This document describes the implementation of the **Evidence Retrieval & Assembly Pipeline**, which orchestrates multiple modules to produce structured, machine-readable evidence payloads for LLM consumption.

### Core Components

1. **`orchestration.py`** - Master controller (Phase 1-4 orchestration)
2. **`assemble_payload.py`** - Payload assembly with filtering & deduplication
3. **`app.py`** - CLI interface for running the pipeline
4. **`vector_engine.py`** - Bi-encoder retrieval + cross-encoder reranking (existing)
5. **`pipeline.py`** - Literature fetching & chunking (existing)

---

## Architecture

### Pipeline Phases (Strict Sequence)

```
Phase 1: fetch_literature
   ↓
Phase 2: process_literature (chunking)
   ↓
Phase 3: vector_engine (retrieval + reranking)
   ↓
Phase 4: assemble_payload (filtering + deduplication)
   ↓
Output: data/context_payload.json
```

### Design Principles

- **Decoupled**: Each phase can be tested independently
- **Loosely Coupled**: Phases don't directly depend on each other's implementation
- **Configurable**: Threshold, max chunks, and other parameters are adjustable
- **Structured**: Output is deterministic JSON, not free-form strings

---

## Phase Details

### Phase 1: Fetch Literature

**Module**: `pipeline.py::fetch_literature_json()`
**Input**: Gene symbol, Variant code
**Output**: JSON file with raw papers (PMIDs, titles, abstracts)

```python
from pipeline import fetch_literature_json

corpus_path = fetch_literature_json("SNCA", "A53T")
# Returns: "data/literature/SNCA_A53T_corpus.json"
```

### Phase 2: Process Literature

**Module**: `pipeline.py::chunk_literature()` (or equivalent)
**Input**: Raw corpus JSON
**Output**: Chunked corpus with text segments linked to PMIDs

```json
[
  {
    "chunk_id": "chunk_001",
    "pmid": "15331649",
    "title": "Effect of A53T on alpha-synuclein...",
    "chunk": "...text segment..."
  }
]
```

### Phase 3: Vector Engine

**Module**: `vector_engine.py::retrieve_evidence()`
**Input**: Query string
**Output**: Top-K ranked results with rerank_score

```python
ranked_results = vector_engine.retrieve_evidence(
    query="steric clash at position 53"
)

# Result format:
[
  {
    "chunk_id": "chunk_001",
    "pmid": "15331649",
    "title": "Effect of A53T on alpha-synuclein...",
    "chunk": "...relevant portion...",
    "score": 0.91,              # from bi-encoder
    "rerank_score": 0.87        # from cross-encoder
  },
  ...
]
```

**Key Features**:
- Bi-encoder: Fast approximate retrieval (Top-50)
- Cross-encoder: Precise reranking (Top-3 final)
- Normalized scores: 0 to 1 range (0.7+ is high confidence)

### Phase 4: Assemble Payload

**Module**: `assemble_payload.py`
**Input**: Query + Ranked results from Phase 3
**Output**: Structured JSON payload

#### Operations (in order):

1. **Threshold Filtering** (Confidence Gate)
   ```python
   score >= 0.7  → Pass
   score <  0.7  → Fallback to best result, flag as "LOW_CONFIDENCE"
   ```
   - Ensures the LLM doesn't over-rely on low-confidence data
   - Gracefully handles edge cases (few papers, low similarity)

2. **Deduplication** (Evidence Diversity)
   ```
   Max 1-2 chunks per unique PMID
   ```
   - Prevents "echo chambers" where the same paper dominates
   - Enforces diversity across different research sources

3. **Deterministic Sorting**
   ```
   Sort by rerank_score (descending)
   ```
   - Most relevant evidence is always first
   - Ensures reproducible, predictable output

4. **Structured Construction**
   ```json
   {
     "status": "success" | "LOW_CONFIDENCE",
     "query": "...",
     "evidence": [
       {
         "text": "...chunk...",
         "pmid": "15331649",
         "title": "...",
         "score": 0.87
       }
     ]
   }
   ```

---

## Configuration Parameters

### Key Thresholds

```python
# assemble_payload.py
CONFIDENCE_THRESHOLD = 0.7      # Minimum score to pass
MAX_CHUNKS_PER_PMID = 2         # Max evidence per paper
OUTPUT_PATH = "data/context_payload.json"

# vector_engine.py
TOP_K_RETRIEVAL = 50            # Bi-encoder candidates
TOP_K_FINAL = 3                 # Final ranked results
```

### Customization

Override defaults when calling the pipeline:

```python
from orchestration import run_full_pipeline

payload = run_full_pipeline(
    gene="SNCA",
    variant="A53T",
    query="steric clash at position 53",
    confidence_threshold=0.75      # Custom threshold
)
```

---

## Usage Examples

### Example 1: Full Pipeline (Default)

```bash
python app.py \
  --gene SNCA \
  --variant A53T \
  --query "steric clash at position 53 alpha-synuclein"
```

### Example 2: Programmatic Usage

```python
from orchestration import run_full_pipeline

payload = run_full_pipeline(
    gene="SNCA",
    variant="A53T",
    query="steric clash at position 53"
)

print(f"Status: {payload['status']}")
print(f"Evidence items: {len(payload['evidence'])}")

# Access evidence
for item in payload['evidence']:
    print(f"  PMID: {item['pmid']}, Score: {item['score']:.3f}")
```

### Example 3: Skip Phases (Testing)

```python
# Test only Phase 3-4
payload = run_full_pipeline(
    gene="SNCA",
    variant="A53T",
    query="steric clash at position 53",
    skip_phases=[1, 2]  # Skip fetch & process
)
```

### Example 4: Custom Threshold

```python
# Strict filtering (require high confidence)
payload = run_full_pipeline(
    gene="SNCA",
    variant="A53T",
    query="steric clash at position 53",
    confidence_threshold=0.85  # Higher threshold
)
```

---

## Output Format

### Success Case

```json
{
  "status": "success",
  "query": "steric clash at position 53",
  "evidence": [
    {
      "text": "A53T substitution disrupts the native fold, inducing a steric clash at position 53...",
      "pmid": "15331649",
      "title": "Effect of A53T on alpha-synuclein misfolding and aggregation",
      "score": 0.91
    },
    {
      "text": "The A53T variant shows increased propensity for β-sheet formation...",
      "pmid": "12345678",
      "title": "Structural consequences of SNCA mutations",
      "score": 0.78
    }
  ]
}
```

Location: `data/context_payload.json`

### Low Confidence Case

When no results meet the threshold but some exist:

```json
{
  "status": "LOW_CONFIDENCE",
  "query": "obscure variant effect",
  "evidence": [
    {
      "text": "...",
      "pmid": "...",
      "title": "...",
      "score": 0.61
    }
  ]
}
```

**Important**: The LLM should interpret `"status": "LOW_CONFIDENCE"` as a signal to be cautious with the evidence.

---

## Testing & Debugging

### Unit Testing

Test individual phases:

```python
# Test Phase 4 only
from assemble_payload import assemble_payload

mock_results = [
    {"chunk": "text1", "pmid": "123", "title": "t1", "rerank_score": 0.9},
    {"chunk": "text2", "pmid": "456", "title": "t2", "rerank_score": 0.8},
]

payload = assemble_payload("query", mock_results, threshold=0.7)
assert len(payload['evidence']) == 2
assert payload['status'] == 'success'
```

### Logging

The orchestration controller logs each phase:

```
2025-04-16 10:30:15 - orchestration - INFO - 🚀 EVIDENCE PIPELINE ORCHESTRATION
2025-04-16 10:30:15 - orchestration - INFO - Gene: SNCA, Variant: A53T
2025-04-16 10:30:15 - orchestration - INFO - 🔍 Phase 1: Fetching literature...
2025-04-16 10:30:20 - orchestration - INFO - ✅ Phase 1 complete: data/literature/SNCA_A53T_corpus.json
2025-04-16 10:30:21 - orchestration - INFO - ⚙️  Phase 2: Processing literature...
...
2025-04-16 10:30:45 - orchestration - INFO - ✅ PIPELINE COMPLETE
```

---

## Error Handling

### Common Scenarios

| Error | Handling |
|-------|----------|
| No papers found | Return empty evidence list with `"status": "success"` |
| All scores below threshold | Return best result with `"status": "LOW_CONFIDENCE"` |
| Invalid corpus path | Raise `FileNotFoundError` with helpful message |
| Vector engine timeout | Re-raise with context about which phase failed |

### Graceful Degradation

The pipeline is designed to **never crash silently**:

- ✓ All exceptions are logged with phase info
- ✓ Fallback behavior is explicitly documented
- ✓ Status field alerts downstream consumers to data quality

---

## Next Steps

### For LLM Integration

The payload from Phase 4 is ready for:

1. **Context Injection**: Pass `evidence` array to prompt
2. **Citation**: Include PMIDs for source attribution
3. **Confidence Gating**: Check `status` before full reliance

Example prompt:

```
You are analyzing variant pathogenicity. Use this evidence:

{evidence_array}

Important: If status is "LOW_CONFIDENCE", be cautious with conclusions.
```

### For Pipeline Enhancement

Potential future improvements:

- [ ] Add confidence re-ranking based on metadata (journal IF, publication date)
- [ ] Support multiple queries (multi-aspect evidence)
- [ ] Add evidence source diversity metrics
- [ ] Implement caching for repeated queries
- [ ] Add human-in-the-loop validation feedback loop

---

## Files Modified/Created

| File | Status | Purpose |
|------|--------|---------|
| `orchestration.py` | ✨ NEW | Master controller (4-phase orchestration) |
| `assemble_payload.py` | ✨ NEW | Payload assembly (filtering, dedup, sort) |
| `app.py` | 🔄 UPDATED | CLI interface + examples |
| `vector_engine.py` | ✅ EXISTING | Bi-encoder + cross-encoder (unchanged) |
| `pipeline.py` | ✅ EXISTING | Literature fetch + chunking (unchanged) |

---

## Summary

The Evidence Pipeline transforms raw literature into structured, actionable evidence for variant interpretation:

1. **Fetch** papers from PubMed/EuroPePMC
2. **Process** into chunks linked to sources
3. **Retrieve** most relevant chunks using embeddings + reranking
4. **Assemble** into machine-readable JSON with confidence flags

The result is **deterministic, traceable, and ready for downstream LLM consumption**.
