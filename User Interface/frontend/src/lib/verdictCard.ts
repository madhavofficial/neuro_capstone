import type { AnalyzeResponse } from '../types/index.ts';

export type VerdictType = 'PATHOGENIC' | 'BENIGN' | 'VUS';

export interface VerdictHeroModel {
  verdictType: VerdictType;
  verdictTitle: string;
  verdictDescription: string;
  hypothesisLiteratureGap: boolean;
  clinvarClinicalRecord: string | null;
  clinvarVariationId: string | null;
  hasRetrievedLiterature: boolean;
  literatureStatusLabel: string;
  deltaV: number | undefined;
  alphaScore: number;
}

const DEFAULT_MULTIMODAL_DESCRIPTION =
  'Epistemic uncertainty is preserved. Cross-audited evidence between AlphaFold structural heuristics, clinical registries, and literature does not show conclusive pathogenic disruption.';

const STRUCTURE_ONLY_HYPOTHESIS_DESCRIPTION =
  'Hypothesis only: no literature evidence was retrieved. Structural predictions are not a confirmed clinical classification.';

const CLINVAR_LITERATURE_GAP_HYPOTHESIS_DESCRIPTION =
  'Hypothesis only: no literature evidence was retrieved. ClinVar records a clinical classification separately, but without retrieved papers this pipeline call remains a hypothesis.';

const PATHOGENIC_MULTIMODAL_DESCRIPTION =
  'Multi-modal evidence confirms deleterious impact: significant structural/conformational disruption or established clinical consensus across pathogenic registries.';

const BENIGN_MULTIMODAL_DESCRIPTION =
  'Multi-modal evidence demonstrates that this amino acid substitution preserves the native fold stability with no significant steric or charge disruption, supported by clinical databases and literature consensus.';

export function resolveVerdictHero(data: AnalyzeResponse): VerdictHeroModel {
  const context = data.context_data as Record<string, any> | null | undefined;
  const physics = data.physics_data as Record<string, any> | null | undefined;
  const clinvar = context?.clinvar as Record<string, any> | null | undefined;
  const alphaMissense = context?.alphamissense_sniper as Record<string, any> | null | undefined;
  const structured = data.structured_reasoning;

  const rawClinvarSig =
    typeof clinvar?.clinical_significance === 'string'
      ? clinvar.clinical_significance.trim()
      : '';
  const clinvarSig = rawClinvarSig.toLowerCase();
  const clinvarVariationId =
    clinvar?.variation_id !== undefined &&
    clinvar?.variation_id !== null &&
    String(clinvar.variation_id).trim() !== ''
      ? String(clinvar.variation_id).trim()
      : null;

  const alphaVerdict = (alphaMissense?.verdict || '').toLowerCase();
  const alphaScore =
    typeof alphaMissense?.score === 'number'
      ? alphaMissense.score
      : Number(alphaMissense?.score);

  const statusStr = (data.status || '').toUpperCase();
  const customBadge = structured?.verdict_badge?.trim() || '';
  const ragStatus = (data.confidence_matrix?.literature_rag || '').toUpperCase();
  const topEvidence = data.evidence && data.evidence.length > 0 ? data.evidence[0] : null;
  const hasRetrievedLiterature = Boolean(topEvidence);

  const isGeneLevelClinvar =
    clinvar?.variant_match === false ||
    String(clinvar?.scope || '').toLowerCase() === 'gene_level' ||
    clinvarSig.startsWith('gene has ');

  const hasClinvarPathogenic = !isGeneLevelClinvar && clinvarSig.includes('pathogenic');
  const hasClinvarBenign = !isGeneLevelClinvar && !hasClinvarPathogenic && clinvarSig.includes('benign');
  const hasClinvarClassification = hasClinvarPathogenic || hasClinvarBenign;
  const clinvarClinicalRecord = rawClinvarSig || null;

  const hasPathogenicCall =
    statusStr.includes('PATHOGENIC') ||
    Boolean(customBadge && customBadge.toUpperCase().includes('PATHOGENIC')) ||
    hasClinvarPathogenic;

  // Any call without retrieved papers must be labeled a hypothesis,
  // even when ClinVar records a clinical class. Guarding on
  // !hasRetrievedLiterature prevents a contradictory payload with
  // non-empty evidence from claiming no papers were retrieved.
  const structureOnlyHypothesis =
    !hasRetrievedLiterature &&
    [
      'STRUCTURAL_DISCOVERY_VUS',
      'PREDICTED_PATHOGENIC_VUS',
    ].includes(statusStr);

  const hypothesisLiteratureGap =
    !hasRetrievedLiterature && (
      structureOnlyHypothesis ||
      ['NULL_RESULTS', 'TIMEOUT_ERROR'].includes(ragStatus) ||
      hasPathogenicCall ||
      hasClinvarClassification
    );

  let verdictType: VerdictType = 'VUS';
  let verdictTitle = 'VARIANT OF UNCERTAIN SIGNIFICANCE (VUS)';
  let verdictDescription = DEFAULT_MULTIMODAL_DESCRIPTION;

  if (hypothesisLiteratureGap) {
    if (structureOnlyHypothesis && !hasClinvarClassification) {
      verdictType = 'VUS';
      verdictTitle = 'HYPOTHESIS: VARIANT OF UNCERTAIN SIGNIFICANCE (VUS)';
      verdictDescription = STRUCTURE_ONLY_HYPOTHESIS_DESCRIPTION;
    } else if (hasClinvarClassification) {
      if (hasClinvarPathogenic) {
        verdictType = 'PATHOGENIC';
        verdictTitle = 'HYPOTHESIS: PATHOGENIC';
      } else {
        verdictType = 'BENIGN';
        verdictTitle = 'HYPOTHESIS: BENIGN';
      }
      verdictDescription = CLINVAR_LITERATURE_GAP_HYPOTHESIS_DESCRIPTION;
    } else if (
      customBadge.toUpperCase().includes('PATHOGENIC') ||
      statusStr.includes('PREDICTED_PATHOGENIC')
    ) {
      verdictType = 'PATHOGENIC';
      verdictTitle = 'HYPOTHESIS: PATHOGENIC';
      verdictDescription = STRUCTURE_ONLY_HYPOTHESIS_DESCRIPTION;
    } else if (
      customBadge.toUpperCase().includes('BENIGN') ||
      (alphaVerdict.includes('benign') && Number.isFinite(alphaScore) && alphaScore < 0.50)
    ) {
      verdictType = 'BENIGN';
      verdictTitle = 'HYPOTHESIS: BENIGN';
      verdictDescription = STRUCTURE_ONLY_HYPOTHESIS_DESCRIPTION;
    } else {
      verdictType = 'VUS';
      verdictTitle = 'HYPOTHESIS: VARIANT OF UNCERTAIN SIGNIFICANCE (VUS)';
      verdictDescription = STRUCTURE_ONLY_HYPOTHESIS_DESCRIPTION;
    }
  } else if (customBadge) {
    if (customBadge.toUpperCase().includes('PATHOGENIC')) {
      verdictType = 'PATHOGENIC';
      verdictTitle = customBadge;
    } else if (customBadge.toUpperCase().includes('BENIGN')) {
      verdictType = 'BENIGN';
      verdictTitle = customBadge;
    } else {
      verdictType = 'VUS';
      verdictTitle = customBadge;
    }
    verdictDescription = structured?.executive_bottom_line || verdictDescription;
  } else if (statusStr.includes('PREDICTED_PATHOGENIC') || hasClinvarPathogenic) {
    verdictType = 'PATHOGENIC';
    verdictTitle = 'PATHOGENIC / LIKELY PATHOGENIC';
    verdictDescription = structured?.executive_bottom_line || PATHOGENIC_MULTIMODAL_DESCRIPTION;
  } else if (
    hasClinvarBenign ||
    (alphaVerdict.includes('benign') && Number.isFinite(alphaScore) && alphaScore < 0.50)
  ) {
    verdictType = 'BENIGN';
    verdictTitle = 'BENIGN / LIKELY BENIGN';
    verdictDescription = structured?.executive_bottom_line || BENIGN_MULTIMODAL_DESCRIPTION;
  } else {
    verdictDescription = structured?.executive_bottom_line || verdictDescription;
  }

  const literatureStatusLabel = hasRetrievedLiterature
    ? 'Top Reranked'
    : hypothesisLiteratureGap || ['NULL_RESULTS', 'TIMEOUT_ERROR'].includes(ragStatus)
      ? 'No Literature Retrieved'
      : 'Curated';

  const rawDeltaV = physics?.deltas?.delta_volume;
  const deltaV = typeof rawDeltaV === 'number' ? rawDeltaV : undefined;

  return {
    verdictType,
    verdictTitle,
    verdictDescription,
    hypothesisLiteratureGap,
    clinvarClinicalRecord,
    clinvarVariationId,
    hasRetrievedLiterature,
    literatureStatusLabel,
    deltaV,
    alphaScore,
  };
}
