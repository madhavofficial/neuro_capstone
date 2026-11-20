# Neuro-Capstone benchmark report

Scored runs are limited to cases where the full pipeline succeeded and GPT-OSS 120B returned an API synthesis. That means the all_evidence setting, with structure, clinical context, physics, literature fetch, literature processing, retrieval, and payload each marked success, and model_meta.mode equal to api. Partial ablations, pipeline failures, and fallback baselines are excluded. Physics is a heuristic and is not treated as a clinical diagnosis.

Recorded runs: 144. Scored runs: 12. Unsettled variants excluded from agreement: 4.

## Summary

| Metric | Value |
|---|---:|
| n_runs | 12 |
| pipeline_completion_rate | 1.0 |
| exact_variant_clinical_lookup_accuracy | 0.9167 |
| literature_relevance_top5 | 0.5476 |
| paper_citation_validity | 0.913 |
| invented_pmid_rate | 0.087 |
| clinical_field_validity | 0.8125 |
| n_gene_context_claims | 0 |
| unsupported_claim_rate | 0.2326 |
| json_schema_validity | 1.0 |
| n_unsettled_excluded | 4 |
| mean_runtime_seconds | 115.847 |
| external_api_failure_rate | 0.0 |
| compatibility_failure_rate | 0.0 |

## Ablation comparison

| Setting | Completion | Top-5 relevance | Citation validity | VUS uncertainty |
|---|---:|---:|---:|---:|
| all_evidence | 1.0 | 0.5476 | 0.913 | None |

## Excluded runs

| Reason | N |
|---|---:|
| partial_pipeline | 81 |
| pipeline_failed | 13 |
| stage_not_successful | 38 |

## Settled literature-class agreement (reference only)

Settled labels come from published literature named in `data/benchmarks/gold_variants.csv`, not ClinVar class strings alone. Variants left unsettled by published reviews are excluded from agreement rather than marked wrong when the model chooses a class. Because only two settled benign/protective variants appear in this 35-variant set (`TTR T139M` protective and `TTR G26S` polymorphism), this table is a reference sanity check rather than a balanced clinical benchmark; blinded rescue-set AUROC is tracked separately.

Overall settled agreement: 0.875 (unsettled excluded: 4).

| Gold class | N | Correct | Agreement |
|---|---:|---:|---:|
| pathogenic | 6 | 6 | 1.0 |
| benign | 2 | 1 | 0.5 |

## Separate Track Benchmarks: Novel (Blinded) vs. Established

| Track | N | Settled Agreement | Unsettled Excluded | Paper Citation Validity | Clinical Field Validity | Unsupported Claim Rate |
|---|---:|---:|---:|---:|---:|---:|
| Established (Full Pipeline / all_evidence) | 12 | 0.875 | 4 | 0.913 | 0.8125 | 0.2326 |
| Novel Blinded (Biophysics Only / physics_only) | 16 | 1.0 | 6 | 0.0 | 0.0 | 1.0 |
| Novel Blinded (No ClinVar / literature_only) | 36 | 0.9643 | 8 | 0.987 | 0.0 | 0.1828 |
| Clinical Lookup Baseline (clinical_only) | 29 | 0.9167 | 5 | 0.0 | 0.6765 | 0.6406 |
