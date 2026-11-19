# Neuro-Capstone benchmark report

Scored runs are limited to cases where the full pipeline succeeded and GPT-OSS 120B returned an API synthesis. That means the all_evidence setting, with structure, clinical context, physics, literature fetch, literature processing, retrieval, and payload each marked success, and model_meta.mode equal to api. Partial ablations, pipeline failures, and fallback baselines are excluded. Physics is a heuristic and is not treated as a clinical diagnosis.

Recorded runs: 144. Scored runs: 20. Unsettled variants excluded from agreement: 3.

## Summary

| Metric | Value |
|---|---:|
| n_runs | 20 |
| pipeline_completion_rate | 1.0 |
| exact_variant_clinical_lookup_accuracy | 1.0 |
| literature_relevance_top5 | 0.7105 |
| citation_validity | 0.6364 |
| unsupported_claim_rate | 0.3636 |
| json_schema_validity | 1.0 |
| n_unsettled_excluded | 3 |
| mean_runtime_seconds | 112.0786 |
| external_api_failure_rate | 0.0 |
| compatibility_failure_rate | 0.0 |

## Ablation comparison

| Setting | Completion | Top-5 relevance | Citation validity | VUS uncertainty |
|---|---:|---:|---:|---:|
| all_evidence | 1.0 | 0.7105 | 0.6364 | None |

## Excluded runs

| Reason | N |
|---|---:|
| gptoss_not_successful | 13 |
| partial_pipeline | 104 |
| pipeline_failed | 7 |

## Settled literature-class agreement (reference only)

Settled labels come from published literature named in `data/benchmarks/gold_variants.csv`, not ClinVar class strings alone. Variants left unsettled by published reviews are excluded from agreement rather than marked wrong when the model chooses a class. Because only two settled benign/protective variants appear in this 36-variant set (`TTR T139M` protective and `TTR G26S` polymorphism), this table is a reference sanity check rather than a balanced clinical benchmark; blinded rescue-set AUROC is tracked separately.

Overall settled agreement: 0.8824 (unsettled excluded: 3).

| Gold class | N | Correct | Agreement |
|---|---:|---:|---:|
| pathogenic | 15 | 14 | 0.9333 |
| benign | 2 | 1 | 0.5 |
