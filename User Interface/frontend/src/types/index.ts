export interface AnalyzeRequest {
  gene: string;
  variant: string;
}

export interface AnalyzeResponse {
  gene: string;
  variant: string;
  context_data?: Record<string, unknown> | null;
  physics_data?: Record<string, unknown> | null;
  pdb_content?: string | null;
  warnings?: Record<string, string> | null;
}

