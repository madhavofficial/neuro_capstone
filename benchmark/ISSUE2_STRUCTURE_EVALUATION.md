# Issue #2 — blinded structure-only evaluation protocol

## Purpose and estimand

This evaluation asks whether the 14 exported structural measurements can
discriminate pathogenic from benign variants when the model is tested on genes
excluded from its training fold. It is not a clinical diagnostic tool and does
not establish prospective clinical utility.

## Inputs and separation

1. `--features`: JSON rows produced by
   `benchmark.feature_vector.build_feature_row`. Each row contains gene,
   variant, AlphaMissense score, and structural features.
2. `--labels`: a separate gold CSV with `gene,variant,label`. Accepted
   labels are Humsavar P/LP and B/LB (or full names).

Labels are joined only after feature validation and are targets, never
predictors. Feature JSON containing ClinVar/clinical classification fields is
rejected. AlphaMissense is not a predictor in the structure-only model; it is
used only to define the prespecified low-score rescue subgroup.

The batch exporter writes feature JSON and a separate label-audit CSV. Never
merge the label audit into the feature JSON.

## Feature handling

The 14 structural measurements are listed in `STRUCTURAL_KEYS` in
`benchmark/structure_only_model.py`. Lost salt-bridge and disulfide lists are
converted to counts. Numeric and categorical imputation is fitted separately
inside each training fold. A feature that is entirely missing in a training
fold is dropped for that fold; test-fold values do not determine feature
selection. Missingness counts and dropped features are written to the report.

The loader rejects non-finite numeric values, invalid pLDDT values outside
[0, 100], negative SASA/contact/hydrogen-bond counts, duplicate identities,
unmatched labels, and forbidden clinical fields.

## Model and validation

- Model: logistic regression with balanced class weights.
- Predictors: structural features only.
- Validation: stratified K-fold cross-validation grouped by gene.
- Metric: AUROC computed from out-of-fold probabilities for all variants.
- A fold lacking either class in train or test causes a hard failure. Do not
  silently change to random variant-level splitting.
- The fold-level report records held-out genes and all-missing training
  predictors.

## Confidence interval

The 95% interval uses a stratified gene-cluster percentile bootstrap over the
out-of-fold predictions. Whole genes are resampled within gene label-profile
strata (pathogenic-only, benign-only, mixed), rather than resampling individual
variants as independent observations. The report records requested and valid
bootstrap draws.

This interval is conditional on the generated out-of-fold predictions. It
does not include uncertainty from model selection, threshold selection,
dataset construction, or upstream structure prediction. If the dataset has
too few genes or too little class diversity across genes, the bootstrap fails
rather than silently reverting to a variant-level interval.

## Rescue definition and threshold preregistration

A rescue candidate is a pathogenic variant with a non-missing AlphaMissense
score below the prespecified low-score cutoff. It is counted as rescued when
its out-of-fold structure-only probability meets or exceeds the prespecified
structure-positive cutoff.

Both cutoffs must be selected, justified, and recorded before inspecting
rescue outcomes. The CLI requires the AlphaMissense cutoff; the structure
probability cutoff is configurable. The example value below is illustrative,
not an endorsed scientific threshold.

## Commands (PowerShell)

Run focused tests:

```powershell
python -m unittest benchmark.test_structure_only_model benchmark.test_batch_feature_export -v
```

Run the complete repository test suite:

```powershell
python -m unittest discover -s . -p "test_*.py" -v
```

Export blinded features:

```powershell
python -m benchmark.batch_feature_export --runs-root data/benchmarks/runs --labels data/benchmarks/humsavar_neuro_100.csv --features-out data/benchmarks/humsavar_neuro_features.json --audit-out data/benchmarks/issue2_label_audit.csv
```

Evaluate after cutoffs have been preregistered:

```powershell
python -m benchmark.structure_only_model --features data/benchmarks/humsavar_neuro_features.json --labels data/benchmarks/humsavar_neuro_100.csv --output data/benchmarks/issue2_structure_only_report.json --alphamissense-low-cutoff 0.34 --structure-positive-cutoff 0.5
```

The example cutoffs above are placeholders only. Obtain team agreement and
record the rationale before running the final rescue analysis.

## Reporting checklist

- [ ] Record dataset filename, version/source, retrieval date, and checksum.
- [ ] Record raw label counts and gene distribution before any audit.
- [ ] Report the raw independent-label analysis separately from any clinically
      audited/consensus-label sensitivity analysis.
- [ ] Record feature coverage, missingness, and excluded variants.
- [ ] Record the exact prespecified cutoffs and rationale.
- [ ] Report gene-grouped OOF AUROC, gene-cluster bootstrap 95% interval,
      fold composition, and number of genes/variants.
- [ ] Report low-AlphaMissense pathogenic count and rescued count/list.
- [ ] State that AlphaMissense is not a model predictor.
- [ ] State the limitations of conditional OOF bootstrap uncertainty.
- [ ] Do not describe audited labels informed by clinical databases as an
      independent blinded gold standard.

## Known limitations

This protocol cannot correct upstream structural modelling errors or label
misclassification. Gene-grouped cross-validation estimates generalization to
held-out genes represented in this dataset, not necessarily to unrelated
clinical populations. The cluster bootstrap is an approximate uncertainty
summary conditional on the OOF predictions. AUROC does not measure calibration,
clinical utility, or decision-threshold performance.
