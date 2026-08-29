export interface AnalyzeRequest {
  gene: string;
  variant: string;
}

export interface LiteratureEvidence {
  title?: string;
  text?: string;
  abstract?: string;
  chunk?: string;
  snippet?: string;
  pmid?: string;
  PMID?: string;
  score?: number;
  relevance?: number;
  score_type?: string;
  [key: string]: unknown;
}

export interface AnalyzeResponse {
  gene: string;
  variant: string;

  /**
   * Actual global status returned by assemble_payload.
   *
   * Examples:
   * SUCCESS
   * LOW_CONFIDENCE
   * STRUCTURAL_DISCOVERY_VUS
   * PREDICTED_PATHOGENIC_VUS
   */
  status?: string | null;

  /**
   * Actual per-engine confidence matrix.
   */
  confidence_matrix?: {
    physics_engine?: string;
    literature_rag?: string;
    clinical_context?: string;
    clinical_context_scope?: string;
    physics_evidence_scope?: string;
    [key: string]: unknown;
  } | null;

  context_data?: Record<string, unknown> | null;

  physics_data?: Record<string, unknown> | null;

  pdb_content?: string | null;

  warnings?: Record<string, string> | null;

  evidence?: LiteratureEvidence[];

  clinical_narrative?: string | null;
}