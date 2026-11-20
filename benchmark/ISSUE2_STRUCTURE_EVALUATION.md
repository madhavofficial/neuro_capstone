# Issue #2 structure-only evaluation

This evaluator is the modelling step that was missing from
`benchmark/blinded_rescue_eval.py`. It turns the 14 structural measurements
into an out-of-fold pathogenicity score; it does not consume ClinVar or
AlphaMissense as model predictors.

## Inputs

1. `--features`: a JSON array of rows returned by
   `benchmark.feature_vector.build_feature_row`. Each row has
   `gene`, `variant`, `alphamissense_score`, and
   `structural_features`.
2. `--labels`: a separate independent gold CSV with columns
   `gene,variant,label`. Labels may be Humsavar `P/LP` or `B/LB`,
   or their full pathogenic/benign names. Do not add labels to the feature JSON.

Feature and label rows are joined on gene + protein substitution. Every feature
row must have a matching gold label. Clinical/ClinVar keys in feature JSON are
rejected. Missing structural numeric values are median-imputed inside each
training fold; categorical values are most-frequent imputed and one-hot encoded.
Lost-contact lists are converted to counts. No imputation is done before CV.

## Method

- Logistic regression with balanced class weights.
- Five-fold stratified cross-validation grouped by gene (configurable).
- AUROC uses only out-of-fold structure-only probabilities.
- The 95% interval is a stratified, variant-level percentile bootstrap over
  out-of-fold predictions. It describes sampling uncertainty conditional on
  these predictions; it does not capture all model-selection uncertainty.
- AlphaMissense is used only to select pathogenic variants below the explicitly
  supplied low-score cutoff. It is not a model feature.
- A rescue is a low-AlphaMissense pathogenic variant whose out-of-fold
  structure-only probability meets the explicitly supplied positive cutoff.

The cutoffs must be selected and recorded before inspecting rescue outcomes.
The script intentionally has no hidden scientific threshold defaults.

## Run

```powershell
python -m benchmark.structure_only_model --features data/benchmarks/humsavar_neuro_features.json --labels data/benchmarks/humsavar_neuro_100.csv --output data/benchmarks/issue2_structure_only_report.json --alphamissense-low-cutoff 0.34 --structure-positive-cutoff 0.5
```

The AlphaMissense cutoff in this example is illustrative only; obtain team
agreement and prespecify it before reporting results. If gene-grouped folds
cannot contain both classes in every train and test split, the script stops
instead of silently switching to a less stringent validation design.

## Tests

```powershell
python -m unittest benchmark.test_structure_only_model -v
```
