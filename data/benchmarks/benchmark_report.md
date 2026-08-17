# Neuro-Capstone benchmark report

Generated from the full stage runner. Physics is a heuristic and is not treated as a clinical diagnosis.

## Summary

| Metric | Value |
|---|---:|
| n_runs | 52 |
| pipeline_completion_rate | 0.0 |
| exact_variant_clinical_lookup_accuracy | None |
| literature_relevance_top5 | None |
| citation_validity | None |
| unsupported_claim_rate | None |
| json_schema_validity | None |
| pathogenic_benign_agreement | None |
| vus_uncertainty_preservation | None |
| mean_runtime_seconds | None |
| external_api_failure_rate | 0.0 |
| compatibility_failure_rate | 1.0 |

## Ablation comparison

| Setting | Completion | Top-5 relevance | Citation validity | VUS uncertainty |
|---|---:|---:|---:|---:|
| clinical_only | 0.0 | None | None | None |
| literature_only | 0.0 | None | None | None |
| physics_only | 0.0 | None | None | None |
| all_evidence | 0.0 | None | None | None |

## Example failures

| Run | Variant | Ablation | Error |
|---|---|---|---|
| a9ea1abbfd015998 | A53T | clinical_only | unsupported operand type(s) for \|: 'type' and 'NoneType' |
| 23880fc3060a7352 | A53T | literature_only | unsupported operand type(s) for \|: 'type' and 'NoneType' |
| ae3de1b7e52ee1fb | A53T | physics_only | unsupported operand type(s) for \|: 'type' and 'NoneType' |
| e0ec583fb71a0678 | A53T | all_evidence | unsupported operand type(s) for \|: 'type' and 'NoneType' |
| e235966352e6b185 | A30P | clinical_only | unsupported operand type(s) for \|: 'type' and 'NoneType' |
| 0fd9f79b17c0f30a | A30P | literature_only | unsupported operand type(s) for \|: 'type' and 'NoneType' |
| a90b702a6103ee12 | A30P | physics_only | unsupported operand type(s) for \|: 'type' and 'NoneType' |
| f73bb2146dcd7202 | A30P | all_evidence | unsupported operand type(s) for \|: 'type' and 'NoneType' |
| 979d61596c6938ee | G51D | clinical_only | unsupported operand type(s) for \|: 'type' and 'NoneType' |
| 3ce97e76e421349c | G51D | literature_only | unsupported operand type(s) for \|: 'type' and 'NoneType' |
| ff1fb8c0e48cedfc | G51D | physics_only | unsupported operand type(s) for \|: 'type' and 'NoneType' |
| 46807057455b249a | G51D | all_evidence | unsupported operand type(s) for \|: 'type' and 'NoneType' |
| ecc20d0c920f5e9e | H50Q | clinical_only | unsupported operand type(s) for \|: 'type' and 'NoneType' |
| db0f7a127f31d91c | H50Q | literature_only | unsupported operand type(s) for \|: 'type' and 'NoneType' |
| c78fed65ca744acb | H50Q | physics_only | unsupported operand type(s) for \|: 'type' and 'NoneType' |
| afa5beeb09316603 | H50Q | all_evidence | unsupported operand type(s) for \|: 'type' and 'NoneType' |
| b969b9c9dc62e676 | A53V | clinical_only | unsupported operand type(s) for \|: 'type' and 'NoneType' |
| 150b0f61768579bf | A53V | literature_only | unsupported operand type(s) for \|: 'type' and 'NoneType' |
| 88d34ef18d8bf946 | A53V | physics_only | unsupported operand type(s) for \|: 'type' and 'NoneType' |
| 7aef82ffdbcf5bcb | A53V | all_evidence | unsupported operand type(s) for \|: 'type' and 'NoneType' |
