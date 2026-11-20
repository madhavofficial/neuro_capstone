# Issue #2 — structure-only blinded rescue evaluation

> Complete this report only after the gold labels and full physics/payload
> artifacts have been received, validated, and exported. Do not fill missing
> values with estimates.

## Dataset provenance

| Field | Value |
|---|---|
| Gold-set file and version | [TO FILL] |
| Source and retrieval date | [TO FILL] |
| Feature/run artifact source | [TO FILL] |
| Dataset checksum (SHA-256) | [TO FILL] |
| Raw variants / genes | [TO FILL] |
| Pathogenic / benign counts | [TO FILL] |

## Label policy

Primary analysis uses the independently sourced raw labels: [TO FILL].
Any clinically audited/consensus-label analysis is a separate sensitivity
analysis and must describe all sources used to revise labels. It must not be
called an independent blinded evaluation if those sources overlap with
pipeline evidence.

## Feature coverage and exclusions

| Measure | Count |
|---|---:|
| Gold variants | [TO FILL] |
| Variants with physics output | [TO FILL] |
| Variants with usable payload | [TO FILL] |
| Feature rows exported | [TO FILL] |
| AlphaMissense score available | [TO FILL] |
| Feature errors / exclusions | [TO FILL] |

Per-feature missingness: [INSERT TABLE FROM JSON REPORT]

## Prespecified evaluation

| Parameter | Value |
|---|---|
| Model | Balanced logistic regression |
| Validation | Stratified gene-grouped K-fold |
| Number of folds | [TO FILL] |
| Random seed | [TO FILL] |
| AlphaMissense low-score cutoff | [TO FILL; preregistered before rescue analysis] |
| Structure-positive cutoff | [TO FILL; preregistered before rescue analysis] |
| Bootstrap | Stratified gene-cluster percentile bootstrap |
| Bootstrap draws requested / valid | [TO FILL] |

## Primary result

- Structure-only out-of-fold AUROC: **[TO FILL]**
- Gene-cluster bootstrap 95% interval: **[TO FILL]**
- Number of variants / genes: **[TO FILL]**
- Fold composition and held-out genes: [INSERT FROM JSON REPORT]

## Low-AlphaMissense rescue analysis

- Pathogenic variants below the prespecified AlphaMissense cutoff: **[TO FILL]**
- Rescued by the prespecified structure-only cutoff: **[TO FILL]**
- Variant identities and OOF scores: [TO FILL]

Do not interpret the rescue count as independent validation of clinical
performance. State the denominator and both thresholds.

## Sensitivity analysis

Raw independent-label results: [TO FILL]

Audited/consensus-label results, if performed: [TO FILL]

Describe disagreements, reclassifications, uncertain variants, and the evidence
used. Keep these results separate from the primary analysis.

## Limitations

- OOF bootstrap interval is conditional on the generated predictions.
- Gene-grouped CV does not establish prospective clinical utility.
- Results depend on upstream structural modelling and feature completeness.
- AUROC does not establish calibration or clinical decision benefit.
- Any audited labels informed by clinical databases are not an independent
  blinded gold standard.

## Reproducibility

Commands, software versions, commit SHA, input checksums, output paths, and
test-suite result: [TO FILL]
