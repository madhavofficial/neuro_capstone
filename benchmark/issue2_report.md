# Issue #2 — Blinded Structure-Only Rescue Evaluation

**Status: Evaluation implementation and CI verified; scientific benchmark execution is blocked by missing input artifacts.**

Last verified implementation commit: `7437f4f8ea7c1455d823cabc74938c3dc29bb636`  
Pull request: [#19](https://github.com/madhavofficial/neuro_capstone/pull/19)  
CI: [Push run #8](https://github.com/madhavofficial/neuro_capstone/actions/runs/44875927201) and [PR run #7](https://github.com/madhavofficial/neuro_capstone/actions/runs/44875922387) — both successful.

## 1. Objective

Test whether structural features alone identify pathogenic variants that fall below a prespecified AlphaMissense score threshold. AlphaMissense is used only to define the low-score rescue subgroup; it is not a predictor in the structure-only model. Labels remain separate from predictor features.

## 2. Implementation completed

- Batch export of structural feature rows from per-variant physics JSON and matching run payloads.
- Separate label CSV; labels are targets, not predictors.
- Rejection of clinical/ClinVar fields in predictor JSON.
- Balanced logistic regression using structural predictors only.
- Stratified gene-grouped cross-validation with out-of-fold predictions.
- Gene-cluster bootstrap confidence interval over out-of-fold predictions.
- Low-AlphaMissense pathogenic subgroup and rescued false-negative count.
- Input validation, missingness reporting, duplicate-run handling, and regression tests.
- Reproducible protocol and results-report template.

## 3. Verification

The Issue #2 focused test suite passed locally: **15 tests, 0 failures**.

The repository GitHub Actions workflow passed on commit `7437f4f`:
- Push workflow run #8: success.
- Pull-request workflow run #7: success.

These checks establish software behaviour. They do not establish scientific benchmark performance.

## 4. Available benchmark evidence — not the requested structure-only result

A separate full-pipeline report dated 2026-11-20 records 100/100 end-to-end pipeline syntheses on the Humsavar-derived set. It reports:
- Raw Humsavar-label exact agreement: 45/100 (45.0%).
- Audited clinical-consensus appropriateness: 89/100 (89.0%).
- Paper citation validity: 107/109 (98.2%).
- Clinical field validity: 85/120 (70.8%).
- Unsupported claim rate: 96/286 (33.6%).

Those are full-pipeline synthesis/audit metrics. They are **not** structure-only AUROC, a structure-only confidence interval, or a structure-only rescue count. The audited consensus uses additional clinical sources and is not an independent blinded gold label. It must be reported separately from the raw Humsavar labels.

## 5. Input-artifact audit

The GitHub branch tree was inspected at the verified implementation commit. It contains:
- Four physics JSON files, representing only two unique variants: SNCA E46K and SNCA A53T (duplicate runs).
- An existing ClinVar-oriented draft gold file, which is not the independent 100-variant Humsavar gold set.
- No `humsavar_neuro_100.csv`.
- No complete 100-variant physics/payload run export.
- No consolidated 100-row structural feature JSON.

The previously supplied full-pipeline PDF does not contain per-variant structural feature vectors or structure-only model scores. Therefore the missing model metrics cannot be reconstructed from that PDF.

## 6. Required handoff to run the evaluation

Provide or push all of the following to the same branch (or attach them to the task):

1. `data/benchmarks/humsavar_neuro_100.csv` — the exact 100-row raw Humsavar gold set, with `gene,variant,label` and source/provenance metadata.
2. The complete per-variant run artifacts under `data/benchmarks/runs/`: one usable `*_physics.json` per gold variant and its sibling `payload.json` containing `clinical_context.alphamissense_sniper.score` (or an equivalent separately sourced AlphaMissense score file with an explicit variant key).
3. A note confirming the coordinate/isoform convention used for each variant, so gene/variant keys match the physics filenames.
4. The source/retrieval date and SHA-256 checksum of the gold CSV and artifact archive.

The exporter can then produce the feature JSON and separate label audit. Missing physics outputs, missing payloads, missing AlphaMissense values, and duplicate runs will be counted rather than silently fabricated.

## 7. Prespecification required before final rescue analysis

The following thresholds must be agreed and recorded before inspecting rescue outcomes:
- AlphaMissense low-score cutoff.
- Structure-only positive-probability cutoff.

The CLI's illustrative values (0.34 and 0.5) are examples only, not validated or endorsed thresholds. Do not report a rescue count until the cutoffs and rationale are preregistered.

## 8. Results

| Required result | Status |
|---|---|
| 100-variant feature export | Blocked — input artifacts not present in inspected branch |
| Feature coverage / missingness | Not available for the 100-variant set |
| Gene-grouped structure-only OOF AUROC | Not run |
| Gene-cluster bootstrap 95% CI | Not run |
| Low-AlphaMissense pathogenic denominator | Not available |
| Structure-only rescued false-negative count/list | Not run |

**No structure-only AUROC, confidence interval, or rescue count is reported.** Reporting values from the two available unique variants, the full-pipeline PDF, or the separate S669 benchmark would be scientifically invalid.

## 9. Reproduction commands

After the required files are present and thresholds are preregistered:

```powershell
python -m benchmark.batch_feature_export --runs-root data/benchmarks/runs --labels data/benchmarks/humsavar_neuro_100.csv --features-out data/benchmarks/humsavar_neuro_features.json --audit-out data/benchmarks/issue2_label_audit.csv
```

Inspect the exporter audit before evaluation. Then run (replace the example thresholds only with the team's preregistered values):

```powershell
python -m benchmark.structure_only_model --features data/benchmarks/humsavar_neuro_features.json --labels data/benchmarks/humsavar_neuro_100.csv --output data/benchmarks/issue2_structure_only_report.json --alphamissense-low-cutoff <PREREGISTERED_AM_CUTOFF> --structure-positive-cutoff <PREREGISTERED_STRUCTURE_CUTOFF>
```

## 10. Conclusion

The implementation, safeguards, tests, and CI are complete and verified. Issue #2 is **not scientifically complete** until the full independent gold set and matching structural/AlphaMissense artifacts are supplied, the thresholds are preregistered, and the actual evaluation report is generated and reviewed.
