# Neuro-Capstone benchmark report

Generated from the full stage runner. Physics is a heuristic and is not treated as a clinical diagnosis.

## Summary

| Metric | Value |
|---|---:|
| n_runs | 144 |
| pipeline_completion_rate | 0.9861 |
| exact_variant_clinical_lookup_accuracy | 0.5 |
| literature_relevance_top5 | 0.7203 |
| citation_validity | None |
| unsupported_claim_rate | None |
| json_schema_validity | 1.0 |
| prediction_accuracy | 0.331 |
| pathogenic_benign_agreement | 0.2759 |
| pathogenic_benign_macro_agreement | 0.2414 |
| vus_uncertainty_preservation | 0.8462 |
| mean_runtime_seconds | 37.4711 |
| external_api_failure_rate | 0.0 |
| compatibility_failure_rate | 0.0 |

## Pathogenic/benign agreement by gold class

| Gold class | N | Correct | Agreement |
|---|---:|---:|---:|
| pathogenic | 68 | 30 | 0.4412 |
| benign | 48 | 2 | 0.0417 |

## Ablation comparison

| Setting | Completion | Top-5 relevance | Citation validity | VUS uncertainty |
|---|---:|---:|---:|---:|
| clinical_only | 1.0 | None | None | 1.0 |
| literature_only | 0.9722 | 0.7203 | None | 1.0 |
| physics_only | 1.0 | None | None | 1.0 |
| all_evidence | 0.9722 | 0.7203 | None | 0.3333 |

## Example failures

| Run | Variant | Ablation | Error |
|---|---|---|---|
| ec33da36c901ce10 | V48M | literature_only | Chunked corpus for TTR V48M contains 0 chunks. The literature fetch likely failed (e.g. Europe PMC timeout). Re-run pipeline after network connectivity is restored to populate the corpus. |
| 061b846ec426663e | V48M | all_evidence | Chunked corpus for TTR V48M contains 0 chunks. The literature fetch likely failed (e.g. Europe PMC timeout). Re-run pipeline after network connectivity is restored to populate the corpus. |
