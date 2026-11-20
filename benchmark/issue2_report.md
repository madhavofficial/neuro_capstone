# Issue #2 — Blinded Rescue Set for Late-Onset Pathogenic Variants

**Status: Partially implemented; scientific evaluation blocked by incomplete data.**

## Scope

The goal is to evaluate whether structure-only features can identify pathogenic missense variants that receive low AlphaMissense scores, including TTR. ClinVar classifications are evaluation labels only and must not be included in model features.

## Implementation completed

- Added `benchmark/blinded_rescue_eval.py` for structure-only AUROC, stratified bootstrap confidence intervals, and low-AlphaMissense rescue counting.
- The evaluator keeps ClinVar labels separate from predictor scores.
- Added input validation for missing scores, duplicate variants, invalid labels, and datasets containing only one class.
- Updated ClinVar resolution to read the germline classification review status and reject records that fail the review-status or curated-label agreement requirements.
- Added tests for the resolver and blinded-rescue evaluator.

## Test results

Full command:

```powershell
python -m unittest discover -s . -p "test_*.py" -v
``r

Result: 88 tests run, 86 passed, 2 skipped, 0 failures.

The two skipped tests require 1DIV.pdb, which was not present. The DSSP warning did not cause a test failure.

These tests validate software behaviour. They do not establish scientific benchmark performance.

## Gold-set status
The existing checked-in benchmark reports 35 verified rows after excluding 9 unresolved candidates. This is not equivalent to the stricter Issue #2 gold set.

The separate strict-review draft contains 44 candidate rows:
- 15 rows pass the current review-status and curated-label agreement filters.
- 29 rows remain unresolved or rejected.
- The accepted rows comprise 14 pathogenic and 1 benign variant.
- The accepted rows cover SNCA, TTR, and MAPT only.
- APP, PSEN1, SOD1, LRRK2, and TARBP are not represented in the current seed.
The strict draft is not a sufficiently balanced evaluation set. The existing gold_variants.csv was not overwritten.

## Structural feature availability
The current local run inventory contains only two unique variant analysis files:
- SNCA E46K
- SNCA A53T
The matching payloads contain AlphaMissense scores for these variants, but this is not a complete feature matrix for the gold set. The E46K record does not pass the current strict ClinVar review filter. A53T is accepted as pathogenic, but its AlphaMissense score is not in the low-score rescue slice.

The current feature exporter provides structural features for individual variants. A complete batch export for the required gold variants is not available in the inspected run data.

## Metrics
Structure-only AUROC: Not reported.

Confidence interval: Not reported.

Rescued false-negative count: Not reported.

These metrics are intentionally withheld because the available data do not provide a complete, balanced, independently verified set of pathogenic and benign variants with matching structural-only scores. Reporting metrics from this incomplete sample would be misleading.

## Leakage safeguards
- ClinVar classification is used as the evaluation target, not as a predictor.
- The Issue #2 evaluator calculates AUROC from structure_only_score.
- The full pipeline benchmark is not used to claim ClinVar prediction performance because its payload can contain ClinVar-derived clinical labels.
- The separate S669 feature dataset is not substituted for the Issue #2 rescue set.

## Remaining work
1. Expand the seed to cover the required genes: SNCA, TTR, MAPT, APP, PSEN1, SOD1, LRRK2, and TARBP.
2. Obtain a sufficiently balanced set of independently verified pathogenic and benign variants meeting the review-status criteria.
3. Generate and verify AlphaMissense and structural feature rows for every included variant.
4. Agree on the low-AlphaMissense cutoff and structure-only positive-score threshold before evaluating the rescue slice.
5. Run the blinded evaluator and report AUROC, confidence interval, and rescued false-negative count.

## Conclusion
The evaluation infrastructure, ClinVar filtering safeguards, and automated tests are in place. Issue #2 is not complete: the current gold set and structural feature coverage are insufficient to produce defensible rescue metrics. No AUROC, confidence interval, or rescue count is fabricated or inferred from the available partial data.
