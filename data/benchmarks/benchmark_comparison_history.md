# Neuro-Capstone Benchmark History & Comparison

This document archives the benchmark run executed on **2026-11-19 / 2026-11-20** (against the pre-audit `gold_variants.csv` after resolving GitHub Issues #9–#17) and compares it against the **prior baseline (`f3f1b05`)**.

---

## Side-by-Side Metric Comparison (Scored Full-Pipeline Runs)

| Metric | Prior Baseline (`f3f1b05`) | Overnight Run (`2026-11-20`) | Delta / Interpretation |
|---|---:|---:|---|
| **Recorded Runs** | 144 | 140 | Duplicate `ttr-a45t` removed (`-4` runs) |
| **Scored Full-Pipeline Runs** | 19 | 8 | 53 runs failed due to upstream Groq rate limits + 404s on deprecated fallback IDs (`llama-3.3-70b-versatile`, `qwen/qwen3-32b`) |
| **Paper Citation Validity** | 65.3% | **92.9%** | **+27.6 pts** — Separating clinical database claims from paper citations (Issue #11) and indexing dbSNP PMIDs into RAG (Issue #9) eliminated false citation penalties |
| **Invented PMID Rate** | *not tracked separately* | **7.1%** | Only 1 of 14 paper citations was outside the retrieved payload evidence |
| **Clinical Field Validity** | *not tracked* | **28.6%** | Strict verification of ClinVar IDs, AlphaMissense scores, and dbSNP frequencies caught ungrounded clinical claims |
| **Unsupported Claim Rate** | 34.7% | **31.8%** | **-2.9 pts** improvement |
| **Literature Top-5 Relevance** | 73.0% | **44.4%** | Evaluated on a smaller N=8 scored subset |
| **Exact Variant Clinical Lookup Accuracy** | 100.0% | **87.5%** | 1 of 8 scored runs lacked an exact ClinVar match |
| **JSON Schema Validity** | 100.0% | **100.0%** | Maintained 100% structured JSON compliance |
| **Pipeline Completion (Scored)** | 100.0% | **100.0%** | Zero compatibility or crash failures |
| **Settled Literature Agreement** | 87.5% (`N=16`) | **60.0%** (`N=5`) | Small scored sample (`3` unsettled excluded; `2/3` pathogenic, `1/2` benign) |
| **Mean Runtime (seconds)** | 113.2s | **132.3s** | +19s due to live API timeouts/retries |

---

## Excluded Runs Breakdown (Overnight Run)

| Exclusion Reason | Count | Root Cause |
|---|---:|---|
| `model_api_failed` | 53 | Primary model hit rate limits (`429`) and fallback cascade hit `404` on retired Groq model IDs (`llama-3.3-70b-versatile`, `qwen/qwen3-32b`) |
| `partial_pipeline` | 52 | Expected ablation runs (`clinical_only`, `literature_only`, `physics_only`) |
| `stage_not_successful` | 15 | ThermoMPNN `residue_mismatch` on isoform-shifted *MAPT* positions |
| `pipeline_failed` | 12 | Upstream network/pipeline failures |

---

## Key Takeaways Leading to Next Run

1. **Citation Grounding Improved Dramatically (+27.6%):** Separating `paper_citation` from `clinical_database` claims and fetching dbSNP PMIDs into the vector corpus worked as intended, pushing `paper_citation_validity` to **92.9%**.
2. **Gold Standard Audit Applied:** Prior to the next run, a deterministic audit against UniProt, ClinVar, and PubMed uncovered and fixed 22 corrupted PMIDs, `mapt-k257t` ClinVar ID mismatch (`3654589` $\to$ `14259`), `ttr-t59a` (`2169602`), `mapt-v300i` (`benign`), and `ttr-v48m` (`pathogenic`).
3. **Fallback Catalog Fix Needed:** `qwen/qwen3-32b` and `llama-3.3-70b-versatile` must be replaced with active Groq model `qwen/qwen3.8-27b` so rate-limited runs do not fail with `HTTP 404`.
