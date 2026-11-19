import assert from "node:assert/strict";
import { resolveVerdictHero } from "./src/lib/verdictCard.ts";
import type { AnalyzeResponse } from "./src/types/index.ts";

function baseResponse(overrides: Partial<AnalyzeResponse> = {}): AnalyzeResponse {
  return {
    gene: "SNCA",
    variant: "A53T",
    status: "SUCCESS",
    confidence_matrix: {
      physics_engine: "HEURISTIC",
      literature_rag: "SUCCESS",
      clinical_context: "HIGH",
    },
    context_data: {},
    physics_data: { deltas: { delta_volume: 27.5 } },
    evidence: [],
    structured_reasoning: null,
    ...overrides,
  };
}

// 1. Issue #17 primary case: no retrieved papers + ClinVar Pathogenic + STRUCTURAL_DISCOVERY_VUS
const noLitClinvarPathogenic = resolveVerdictHero(
  baseResponse({
    status: "STRUCTURAL_DISCOVERY_VUS",
    confidence_matrix: {
      physics_engine: "HEURISTIC",
      literature_rag: "NULL_RESULTS",
      clinical_context: "HIGH",
    },
    context_data: {
      clinvar: {
        clinical_significance: "Pathogenic",
        variation_id: "14010",
      },
    },
    evidence: [],
    structured_reasoning: {
      verdict_badge: "PATHOGENIC",
      executive_bottom_line: "Model summary that must not override the hypothesis sentence.",
    },
  }),
);
assert.equal(noLitClinvarPathogenic.hypothesisLiteratureGap, true);
assert.equal(noLitClinvarPathogenic.verdictType, "PATHOGENIC");
assert.match(noLitClinvarPathogenic.verdictTitle, /HYPOTHESIS/i);
assert.notEqual(noLitClinvarPathogenic.verdictTitle, "Pathogenic");
assert.equal(noLitClinvarPathogenic.clinvarClinicalRecord, "Pathogenic");
assert.equal(noLitClinvarPathogenic.clinvarVariationId, "14010");
assert.match(noLitClinvarPathogenic.verdictDescription, /^Hypothesis only: no literature evidence was retrieved\./);
assert.doesNotMatch(noLitClinvarPathogenic.verdictDescription, /Epistemic uncertainty is preserved/);
assert.equal(noLitClinvarPathogenic.literatureStatusLabel, "No Literature Retrieved");

// 2. No retrieved papers + ClinVar Benign (even without explicit NULL_RESULTS ragStatus)
const noLitClinvarBenign = resolveVerdictHero(
  baseResponse({
    status: "LOW_CONFIDENCE",
    confidence_matrix: {
      physics_engine: "HEURISTIC",
      literature_rag: "",
      clinical_context: "HIGH",
    },
    context_data: {
      clinvar: {
        clinical_significance: "Likely benign",
        variation_id: "99123",
      },
    },
    evidence: [],
  }),
);
assert.equal(noLitClinvarBenign.hypothesisLiteratureGap, true);
assert.equal(noLitClinvarBenign.verdictType, "BENIGN");
assert.match(noLitClinvarBenign.verdictTitle, /HYPOTHESIS/i);
assert.notEqual(noLitClinvarBenign.verdictTitle, "Likely benign");
assert.equal(noLitClinvarBenign.clinvarClinicalRecord, "Likely benign");
assert.equal(noLitClinvarBenign.clinvarVariationId, "99123");
assert.match(noLitClinvarBenign.verdictDescription, /^Hypothesis only: no literature evidence was retrieved\./);
assert.doesNotMatch(noLitClinvarBenign.verdictDescription, /Epistemic uncertainty is preserved/);
assert.equal(noLitClinvarBenign.literatureStatusLabel, "No Literature Retrieved");

// 3. No retrieved papers + no ClinVar + STRUCTURAL_DISCOVERY_VUS
const structureOnlyNoClinvar = resolveVerdictHero(
  baseResponse({
    status: "STRUCTURAL_DISCOVERY_VUS",
    confidence_matrix: {
      physics_engine: "HEURISTIC",
      literature_rag: "NULL_RESULTS",
      clinical_context: "PARTIAL",
    },
    context_data: {},
    evidence: [],
  }),
);
assert.equal(structureOnlyNoClinvar.hypothesisLiteratureGap, true);
assert.equal(structureOnlyNoClinvar.verdictType, "VUS");
assert.match(structureOnlyNoClinvar.verdictTitle, /HYPOTHESIS/i);
assert.equal(structureOnlyNoClinvar.clinvarClinicalRecord, null);
assert.match(structureOnlyNoClinvar.verdictDescription, /^Hypothesis only: no literature evidence was retrieved\./);

// 4. No retrieved papers + no ClinVar + custom pathogenic badge (not STRUCTURAL_DISCOVERY_VUS)
const noLitCustomPathogenic = resolveVerdictHero(
  baseResponse({
    status: "LOW_CONFIDENCE",
    confidence_matrix: {
      physics_engine: "HEURISTIC",
      literature_rag: "NULL_RESULTS",
      clinical_context: "UNAVAILABLE",
    },
    context_data: {},
    evidence: [],
    structured_reasoning: {
      verdict_badge: "PATHOGENIC",
      executive_bottom_line: "Unverified LLM summary.",
    },
  }),
);
assert.equal(noLitCustomPathogenic.hypothesisLiteratureGap, true);
assert.equal(noLitCustomPathogenic.verdictType, "PATHOGENIC");
assert.match(noLitCustomPathogenic.verdictTitle, /HYPOTHESIS/i);
assert.match(noLitCustomPathogenic.verdictDescription, /^Hypothesis only: no literature evidence was retrieved\./);
assert.doesNotMatch(noLitCustomPathogenic.verdictDescription, /Epistemic uncertainty is preserved/);

// 5. Retrieved papers present + ClinVar Pathogenic (normal multimodal verdict, NOT hypothesis)
const withLitClinvarPathogenic = resolveVerdictHero(
  baseResponse({
    status: "SUCCESS",
    confidence_matrix: {
      physics_engine: "HEURISTIC",
      literature_rag: "SUCCESS",
      clinical_context: "HIGH",
    },
    context_data: {
      clinvar: {
        clinical_significance: "Pathogenic",
        variation_id: "14010",
      },
    },
    evidence: [
      {
        pmid: "9197268",
        title: "Mutation in the alpha-synuclein gene identified in families with Parkinson's disease.",
        text: "A53T causes familial Parkinson's disease.",
        score: 0.95,
      },
    ],
  }),
);
assert.equal(withLitClinvarPathogenic.hypothesisLiteratureGap, false);
assert.equal(withLitClinvarPathogenic.verdictType, "PATHOGENIC");
assert.equal(withLitClinvarPathogenic.verdictTitle, "PATHOGENIC / LIKELY PATHOGENIC");
assert.equal(withLitClinvarPathogenic.clinvarClinicalRecord, "Pathogenic");
assert.match(withLitClinvarPathogenic.verdictDescription, /Multi-modal evidence confirms deleterious impact/);
assert.equal(withLitClinvarPathogenic.literatureStatusLabel, "Top Reranked");

// 6. Retrieved papers present + custom badge + executive_bottom_line
const withLitCustomBadge = resolveVerdictHero(
  baseResponse({
    status: "SUCCESS",
    context_data: {
      clinvar: {
        clinical_significance: "Pathogenic",
      },
    },
    evidence: [{ pmid: "9197268", title: "Paper", text: "Text", score: 0.9 }],
    structured_reasoning: {
      verdict_badge: "CLINVAR_PATHOGENIC",
      executive_bottom_line: "Confirmed by ClinVar and peer-reviewed literature.",
    },
  }),
);
assert.equal(withLitCustomBadge.hypothesisLiteratureGap, false);
assert.equal(withLitCustomBadge.verdictType, "PATHOGENIC");
assert.equal(withLitCustomBadge.verdictTitle, "CLINVAR_PATHOGENIC");
assert.equal(
  withLitCustomBadge.verdictDescription,
  "Confirmed by ClinVar and peer-reviewed literature.",
);

// 7. Retrieved papers present + no ClinVar + no custom badge -> default VUS multimodal sentence
const withLitDefaultVus = resolveVerdictHero(
  baseResponse({
    status: "SUCCESS",
    context_data: {},
    evidence: [{ pmid: "12345678", title: "Paper", text: "Text", score: 0.8 }],
  }),
);
assert.equal(withLitDefaultVus.hypothesisLiteratureGap, false);
assert.equal(withLitDefaultVus.verdictType, "VUS");
assert.equal(withLitDefaultVus.verdictTitle, "VARIANT OF UNCERTAIN SIGNIFICANCE (VUS)");
assert.match(withLitDefaultVus.verdictDescription, /Epistemic uncertainty is preserved/);

console.log("verdict card checks passed");
