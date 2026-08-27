# Neuro-Capstone benchmark report

Generated from the full stage runner. Physics is a heuristic and is not treated as a clinical diagnosis.

## Summary

| Metric | Value |
|---|---:|
| n_runs | 8 |
| pipeline_completion_rate | 1.0 |
| exact_variant_clinical_lookup_accuracy | 0.5 |
| literature_relevance_top5 | 0.8889 |
| citation_validity | None |
| unsupported_claim_rate | None |
| json_schema_validity | 1.0 |
| pathogenic_benign_agreement | 0.5 |
| vus_uncertainty_preservation | None |
| mean_runtime_seconds | 55.4282 |
| external_api_failure_rate | 0.0 |
| compatibility_failure_rate | 0.0 |

## Ablation comparison

| Setting | Completion | Top-5 relevance | Citation validity | VUS uncertainty |
|---|---:|---:|---:|---:|
| clinical_only | 1.0 | None | None | None |
| literature_only | 1.0 | 0.8889 | None | None |
| physics_only | 1.0 | None | None | None |
| all_evidence | 1.0 | 0.8889 | None | None |

## Example failures

| Run | Variant | Ablation | Error |
|---|---|---|---|
