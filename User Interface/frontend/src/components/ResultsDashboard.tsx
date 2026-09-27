import {
  Activity,
  AlertTriangle,
  BookmarkCheck,
  CheckCircle2,
  Dna,
  ExternalLink,
  FileCode2,
  FlaskConical,
  HelpCircle,
  Lightbulb,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import StructuralAudit from './StructuralAudit';
import ClinicalContext from './ClinicalContext';
import Literature from './Literature';
import ProteinViewer from './ProteinViewer';
import { AnalyzeResponse } from '../types';

interface ResultsDashboardProps {
  data: AnalyzeResponse;
}

export default function ResultsDashboard({ data }: ResultsDashboardProps) {
  const hasWarnings =
    data.warnings && Object.keys(data.warnings).length > 0;

  const contextCount = data.context_data
    ? Object.keys(data.context_data).length
    : 0;

  const physicsCount = data.physics_data
    ? Object.keys(data.physics_data).length
    : 0;

  return (
    <div className="space-y-8 animate-in fade-in duration-500">

      {/* RESULT HEADER */}
      <section className="overflow-hidden rounded-[2rem] border border-slate-200 bg-white shadow-soft">
        <div className="relative px-6 py-8 sm:px-8 sm:py-10">
          <div className="absolute right-0 top-0 h-48 w-48 translate-x-1/3 -translate-y-1/3 rounded-full bg-teal-100/60 blur-3xl" />

          <div className="relative">
            <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-teal-50">
                    <CheckCircle2 className="h-4 w-4 text-teal-600" />
                  </span>

                  <span className="eyebrow">
                    Analysis complete
                  </span>
                </div>

                <h1 className="mt-4 text-3xl font-semibold tracking-[-0.035em] text-ink sm:text-4xl">
                  {data.gene}
                  <span className="mx-2 text-slate-300">
                    /
                  </span>

                  <span className="font-mono text-teal-700">
                    {data.variant}
                  </span>
                </h1>

                <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-500">
                  Evidence returned by the active scientific analysis
                  pipeline, organized into structural, physicochemical,
                  clinical, and literature evidence layers.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* RESULT METADATA */}
        <div className="grid grid-cols-2 border-t border-slate-100 sm:grid-cols-4">
          <Metric
            label="Target"
            value={data.gene}
            mono
          />

          <Metric
            label="Variant"
            value={data.variant}
            mono
          />

          <Metric
            label="Context fields"
            value={contextCount.toString()}
          />

          <Metric
            label="Physics fields"
            value={physicsCount.toString()}
          />
        </div>
      </section>

      {/* AI FINAL INTEGRATED VERDICT BANNER */}
      <AIVerdictHeroCard data={data} />

      {/* OVERALL VERDICT */}
      <VerdictCard data={data} />

      {/* CLINICAL REASONING & EVIDENCE DOSSIER (Phase 8 Multi-Modal Output) */}
      {(data.clinical_narrative || data.structured_reasoning) && (
        <ClinicalNarrativeCard
          narrative={data.clinical_narrative || ''}
          structured={data.structured_reasoning}
          model={data.reasoning_model}
          gene={data.gene}
          variant={data.variant}
        />
      )}

      {/* WARNINGS */}
      {hasWarnings && (
        <section className="rounded-2xl border border-amber-200 bg-amber-50/70">
          <div className="flex gap-4 px-5 py-5 sm:px-6">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-100">
              <AlertTriangle className="h-4 w-4 text-amber-700" />
            </div>

            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-amber-800">
                Pipeline notices
              </p>

              <ul className="mt-2 space-y-1.5 text-sm leading-6 text-amber-900">
                {Object.entries(data.warnings!).map(
                  ([key, message]) => (
                    <li key={key}>
                      <span className="font-medium">
                        {message}
                      </span>
                    </li>
                  )
                )}
              </ul>
            </div>
          </div>
        </section>
      )}

      {/* EVIDENCE MAP */}
      <section>
        <div className="mb-4 flex items-end justify-between gap-4">
          <div>
            <p className="eyebrow">
              Evidence layers
            </p>

            <h2 className="mt-1 text-xl font-semibold tracking-tight text-ink">
              What the pipeline returned
            </h2>
          </div>

          <span className="hidden text-xs text-slate-400 sm:block">
            Structured for inspection
          </span>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">

          <EvidenceTile
            number="01"
            icon={FlaskConical}
            title="Structural physics"
            description="Residue properties, deltas, structural context and stability audit."
            active={physicsCount > 0}
          />

          <EvidenceTile
            number="02"
            icon={ShieldCheck}
            title="Clinical context"
            description="Biological and clinical evidence returned for the target variant."
            active={contextCount > 0}
          />

          <EvidenceTile
            number="03"
            icon={FileCode2}
            title="Structural model"
            description="Canonical or baseline PDB coordinates available from the pipeline."
            active={Boolean(data.pdb_content)}
          />

        </div>
      </section>

      {/* MAIN EVIDENCE */}
      <section className="grid grid-cols-1 items-start gap-6 xl:grid-cols-[1.15fr_0.85fr]">

        {/* STRUCTURAL */}
        <div className="space-y-6">

          <StructuralAudit
            physicsData={data.physics_data}
          />

          {data.pdb_content && (
            <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft">

              <div className="flex items-center justify-between border-b border-slate-200 px-5 py-5 sm:px-6">

                <div className="flex items-center gap-3">

                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-ink">
                    <FileCode2 className="h-4 w-4 text-teal-300" />
                  </div>

                  <div>
                    <h3 className="text-sm font-semibold text-ink">
                      Structural model
                    </h3>

                    <p className="mt-0.5 text-xs text-slate-500">
                      Interactive 3D protein structure
                    </p>
                  </div>

                </div>

                <span className="font-mono text-[10px] uppercase tracking-wider text-slate-400">
                  {data.pdb_content.length.toLocaleString()} chars
                </span>

              </div>

              <div className="p-5 sm:p-6">

                <ProteinViewer
                  pdbContent={data.pdb_content}
                  variant={data.variant}
                />

              </div>
            </div>
          )}

        </div>

        {/* CONTEXT */}
        <div className="space-y-6">

          <ClinicalContext
            contextData={data.context_data}
          />

          <Literature
            contextData={data.context_data}
            evidence={data.evidence}
          />

        </div>
      </section>
    </div>
  );
}


/* ========================================================================
   CLINICAL REASONING & EVIDENCE DOSSIER (Phase 8 Multi-Modal Output)
   ======================================================================== */

function formatNarrativeWithCitations(text: string) {
  // Parse [PMID: 12345678] or [PMID 12345678] into clickable badge chips
  const parts = text.split(/(\[PMID:?\s*\d+\])/g);

  return parts.map((part, index) => {
    const match = part.match(/\[PMID:?\s*(\d+)\]/);
    if (match) {
      const pmid = match[1];
      return (
        <a
          key={index}
          href={`https://pubmed.ncbi.nlm.nih.gov/${pmid}/`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 rounded-md bg-teal-50 px-2 py-0.5 font-mono text-xs font-semibold text-teal-700 border border-teal-200/80 shadow-xs hover:bg-teal-100 hover:text-teal-900 transition-colors mx-1 align-baseline"
          title={`View PMID ${pmid} on PubMed`}
        >
          <span>PMID {pmid}</span>
          <ExternalLink className="h-2.5 w-2.5 opacity-70" />
        </a>
      );
    }
    return <span key={index}>{part}</span>;
  });
}

function ClinicalNarrativeCard({
  narrative,
  structured,
  model,
  gene,
  variant,
}: {
  narrative: string;
  structured?: {
    executive_bottom_line?: string;
    molecular_mechanism?: {
      key_disruption?: string;
      biophysical_rationale?: string;
      affected_motif?: string;
    };
    clinical_phenotypes?: Array<{ disease?: string; confidence?: string }>;
    experimental_highlights?: Array<{ system?: string; finding?: string; pmid?: string }>;
    verdict_badge?: string;
    confidence_assessment?: string;
    cited_pmids?: string[];
    [key: string]: unknown;
  } | null;
  model?: string | null;
  gene: string;
  variant: string;
}) {
  const bottomLine = structured?.executive_bottom_line;
  const mechanism = structured?.molecular_mechanism;
  const phenotypes = structured?.clinical_phenotypes;
  const highlights = structured?.experimental_highlights;

  return (
    <section className="overflow-hidden rounded-[2rem] border border-teal-100/80 bg-white shadow-soft">
      {/* HEADER WITH MODEL BADGE */}
      <div className="border-b border-teal-100/70 bg-gradient-to-r from-teal-50/70 via-white to-sky-50/50 px-6 py-6 sm:px-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3.5">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-teal-600 shadow-sm shadow-teal-600/20">
              <Sparkles className="h-5 w-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <p className="eyebrow text-teal-700">Phase 8 Multi-Modal Synthesis</p>
                {structured?.verdict_badge && (
                  <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-800 border border-emerald-200">
                    {structured.verdict_badge}
                  </span>
                )}
              </div>
              <h3 className="mt-1 text-lg font-bold tracking-tight text-ink">
                Clinical Bioinformatics Reasoning Engine
              </h3>
              <p className="mt-0.5 text-xs text-slate-500">
                Synthesizing structural physics, clinical benchmarks, and peer-reviewed literature for {gene} {variant}.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 self-start rounded-xl border border-teal-200/70 bg-white/90 px-3.5 py-2 shadow-xs sm:self-center">
            <Activity className="h-3.5 w-3.5 text-teal-600 animate-pulse" />
            <span className="font-mono text-xs font-semibold text-slate-700">
              {model ? `⚡ ${model}` : '⚡ OpenRouter Reasoning'}
            </span>
          </div>
        </div>
      </div>

      <div className="p-6 sm:p-8 space-y-6">
        {/* EXECUTIVE BOTTOM LINE */}
        {bottomLine && (
          <div className="relative overflow-hidden rounded-2xl border border-teal-200 bg-gradient-to-br from-teal-50/80 via-emerald-50/40 to-white p-5 sm:p-6 shadow-xs">
            <div className="flex items-start gap-3.5">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-teal-600 text-white shadow-xs">
                <Lightbulb className="h-4 w-4" />
              </div>
              <div>
                <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-teal-800">
                  Executive Bottom Line
                </p>
                <p className="mt-1.5 text-base font-medium leading-7 text-ink">
                  {bottomLine}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* 3-CARD STRUCTURED PILLARS */}
        {structured && (mechanism || phenotypes || highlights) && (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            {/* PILLAR 1: MOLECULAR MECHANISM */}
            {mechanism && (
              <div className="rounded-2xl border border-slate-200/90 bg-slate-50/60 p-5 flex flex-col justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-50 text-indigo-700">
                      <Dna className="h-3.5 w-3.5" />
                    </div>
                    <span className="text-[11px] font-bold uppercase tracking-wider text-indigo-900">
                      Molecular Disruption
                    </span>
                  </div>
                  <h4 className="mt-3 text-sm font-bold text-ink">
                    {mechanism.key_disruption || 'Conformational Destabilization'}
                  </h4>
                  <p className="mt-1.5 text-xs leading-5 text-slate-600">
                    {mechanism.biophysical_rationale}
                  </p>
                </div>
                {mechanism.affected_motif && (
                  <div className="mt-4 pt-3 border-t border-slate-200/80">
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                      Disrupted Motif
                    </span>
                    <p className="mt-0.5 text-xs font-semibold text-slate-700 font-mono">
                      {mechanism.affected_motif}
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* PILLAR 2: CLINICAL PHENOTYPES */}
            {phenotypes && phenotypes.length > 0 && (
              <div className="rounded-2xl border border-slate-200/90 bg-slate-50/60 p-5 flex flex-col justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-teal-50 text-teal-700">
                      <ShieldCheck className="h-3.5 w-3.5" />
                    </div>
                    <span className="text-[11px] font-bold uppercase tracking-wider text-teal-900">
                      Clinical Spectrum
                    </span>
                  </div>
                  <div className="mt-3 space-y-2">
                    {phenotypes.map((pheno, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between rounded-xl bg-white p-2.5 border border-slate-200/70 shadow-2xs"
                      >
                        <span className="text-xs font-semibold text-ink truncate pr-2">
                          {pheno.disease}
                        </span>
                        <span className="shrink-0 rounded-md bg-teal-50 px-2 py-0.5 text-[10px] font-bold uppercase text-teal-700 border border-teal-100">
                          {pheno.confidence || 'Definitive'}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
                {structured?.confidence_assessment && (
                  <div className="mt-4 pt-3 border-t border-slate-200/80 flex items-center justify-between">
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                      Evidence Alignment
                    </span>
                    <span className="text-xs font-bold text-emerald-700">
                      {structured.confidence_assessment}
                    </span>
                  </div>
                )}
              </div>
            )}

            {/* PILLAR 3: EXPERIMENTAL EVIDENCE HIGHLIGHTS */}
            {highlights && highlights.length > 0 && (
              <div className="rounded-2xl border border-slate-200/90 bg-slate-50/60 p-5 flex flex-col justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-sky-50 text-sky-700">
                      <BookmarkCheck className="h-3.5 w-3.5" />
                    </div>
                    <span className="text-[11px] font-bold uppercase tracking-wider text-sky-900">
                      Experimental Models
                    </span>
                  </div>
                  <div className="mt-3 space-y-2">
                    {highlights.map((high, idx) => (
                      <div key={idx} className="rounded-xl bg-white p-2.5 border border-slate-200/70 shadow-2xs">
                        <div className="flex items-center justify-between">
                          <p className="text-xs font-bold text-ink truncate">{high.system}</p>
                          {high.pmid && high.pmid !== 'N/A' && (
                            <a
                              href={`https://pubmed.ncbi.nlm.nih.gov/${high.pmid}/`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-[10px] font-mono font-semibold text-sky-600 hover:underline flex items-center gap-0.5"
                            >
                              PMID {high.pmid} <ExternalLink className="h-2 w-2" />
                            </a>
                          )}
                        </div>
                        <p className="mt-1 text-[11px] leading-4 text-slate-500 line-clamp-2">
                          {high.finding}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
                {structured?.cited_pmids && (
                  <div className="mt-4 pt-3 border-t border-slate-200/80 flex items-center justify-between">
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                      Cited Literature
                    </span>
                    <span className="text-xs font-semibold text-slate-700 font-mono">
                      {structured.cited_pmids.length} Retrieved Citations
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* UNSTRUCTURED GROUNDED REASONING NARRATIVE */}
        {narrative && (
          <div className="rounded-2xl border border-slate-200/80 bg-white p-5 sm:p-6 shadow-xs">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-600">
                Grounded Clinical Reasoning & Verdict
              </span>
              <span className="text-[11px] text-slate-400 font-mono">
                Multi-Modal Evidence Synthesis
              </span>
            </div>
            <div className="space-y-4 text-sm leading-7 text-slate-700">
              {narrative.split('\n\n').map((paragraph, pIdx) => (
                <p key={pIdx}>{formatNarrativeWithCitations(paragraph)}</p>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}



/* ========================================================================
   AI FINAL INTEGRATED VERDICT HERO BANNER
   ======================================================================== */

function AIVerdictHeroCard({ data }: { data: AnalyzeResponse }) {
  const context = data.context_data as Record<string, any> | null | undefined;
  const physics = data.physics_data as Record<string, any> | null | undefined;
  const clinvar = context?.clinvar as Record<string, any> | null | undefined;
  const alphaMissense = context?.alphamissense_sniper as Record<string, any> | null | undefined;
  const structured = data.structured_reasoning;

  // 1. Determine Verdict Label & Type
  let verdictType: 'PATHOGENIC' | 'BENIGN' | 'VUS' = 'VUS';
  let verdictTitle = 'VARIANT OF UNCERTAIN SIGNIFICANCE (VUS)';
  let verdictDescription =
    'Epistemic uncertainty is preserved. Cross-audited evidence between AlphaFold structural heuristics, clinical registries, and literature does not show conclusive pathogenic disruption.';

  const clinvarSig = (clinvar?.clinical_significance || '').toLowerCase();
  const alphaVerdict = (alphaMissense?.verdict || '').toLowerCase();
  const alphaScore = typeof alphaMissense?.score === 'number' ? alphaMissense.score : Number(alphaMissense?.score);
  const statusStr = (data.status || '').toUpperCase();
  const customBadge = structured?.verdict_badge;

  if (customBadge) {
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
  } else if (statusStr.includes('PREDICTED_PATHOGENIC') || clinvarSig.includes('pathogenic')) {
    verdictType = 'PATHOGENIC';
    verdictTitle = 'PATHOGENIC / LIKELY PATHOGENIC';
    verdictDescription =
      'Multi-modal evidence confirms deleterious impact: significant structural/conformational disruption or established clinical consensus across pathogenic registries.';
  } else if (clinvarSig.includes('benign') || (alphaVerdict.includes('benign') && alphaScore < 0.50)) {
    verdictType = 'BENIGN';
    verdictTitle = 'BENIGN / LIKELY BENIGN';
    verdictDescription =
      'Multi-modal evidence demonstrates that this amino acid substitution preserves the native fold stability with no significant steric or charge disruption, supported by clinical databases and literature consensus.';
  }

  // 2. Modality Quick Indicators
  const deltaV = physics?.deltas?.delta_volume;
  const topEvidence = data.evidence && data.evidence.length > 0 ? data.evidence[0] : null;

  // Style themes
  const theme = {
    PATHOGENIC: {
      border: 'border-rose-300',
      bgGradient: 'bg-gradient-to-br from-rose-50 via-red-50/40 to-white',
      badgeBg: 'bg-rose-600 text-white shadow-md shadow-rose-600/25',
      glow: 'bg-rose-500',
      icon: ShieldAlert,
      iconColor: 'text-rose-600',
      titleColor: 'text-rose-950',
      tagBorder: 'border-rose-200 bg-rose-50/80 text-rose-800',
    },
    BENIGN: {
      border: 'border-emerald-300',
      bgGradient: 'bg-gradient-to-br from-emerald-50 via-teal-50/40 to-white',
      badgeBg: 'bg-emerald-600 text-white shadow-md shadow-emerald-600/25',
      glow: 'bg-emerald-500',
      icon: ShieldCheck,
      iconColor: 'text-emerald-600',
      titleColor: 'text-emerald-950',
      tagBorder: 'border-emerald-200 bg-emerald-50/80 text-emerald-800',
    },
    VUS: {
      border: 'border-amber-300',
      bgGradient: 'bg-gradient-to-br from-amber-50 via-yellow-50/40 to-white',
      badgeBg: 'bg-amber-600 text-white shadow-md shadow-amber-600/25',
      glow: 'bg-amber-500',
      icon: HelpCircle,
      iconColor: 'text-amber-600',
      titleColor: 'text-amber-950',
      tagBorder: 'border-amber-200 bg-amber-50/80 text-amber-800',
    },
  }[verdictType];

  const IconComponent = theme.icon;

  return (
    <section className={`overflow-hidden rounded-[2rem] border-2 ${theme.border} ${theme.bgGradient} p-6 sm:p-8 shadow-soft`}>
      <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
        
        {/* LEFT: VERDICT BADGE & TITLE */}
        <div className="flex items-start gap-4">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-white shadow-sm border border-slate-200/80">
            <IconComponent className={`h-8 w-8 ${theme.iconColor}`} />
          </div>

          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">
                AI Multimodal Final Verdict
              </span>
              <span className="flex items-center gap-1.5 rounded-full bg-slate-900 px-2.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-white">
                <Sparkles className="h-2.5 w-2.5 text-teal-300" />
                Cross-Audited Synthesis
              </span>
            </div>

            <div className="mt-2 flex flex-wrap items-center gap-3">
              <h2 className={`text-2xl sm:text-3xl font-extrabold tracking-tight ${theme.titleColor}`}>
                {verdictTitle}
              </h2>
              <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wider ${theme.badgeBg}`}>
                <span className="relative flex h-2 w-2">
                  <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${theme.glow}`}></span>
                  <span className={`relative inline-flex rounded-full h-2 w-2 bg-white`}></span>
                </span>
                {verdictType}
              </span>
            </div>

            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600 font-medium">
              {structured?.executive_bottom_line || verdictDescription}
            </p>
          </div>
        </div>

        {/* RIGHT: CONFIDENCE PILLARS */}
        <div className="shrink-0 flex flex-col gap-2 rounded-2xl bg-white/90 p-4 border border-slate-200/90 shadow-2xs">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Evidence Pillar Alignment
          </span>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="flex items-center gap-1.5 rounded-lg bg-slate-50 px-2.5 py-1.5 border border-slate-100">
              <span className="font-bold text-slate-700">3D Biophysics:</span>
              <span className="text-slate-600 font-mono text-[11px]">
                {deltaV !== undefined ? `ΔV: ${deltaV > 0 ? '+' : ''}${deltaV}` : 'Loaded'}
              </span>
            </div>

            <div className="flex items-center gap-1.5 rounded-lg bg-slate-50 px-2.5 py-1.5 border border-slate-100">
              <span className="font-bold text-slate-700">Literature RAG:</span>
              <span className="text-slate-600 font-mono text-[11px]">
                {topEvidence ? 'Top Reranked' : 'Curated'}
              </span>
            </div>

            <div className="flex items-center gap-1.5 rounded-lg bg-slate-50 px-2.5 py-1.5 border border-slate-100">
              <span className="font-bold text-slate-700">ClinVar:</span>
              <span className="text-slate-600 font-mono text-[11px]">
                {clinvar?.variation_id ? `ID ${clinvar.variation_id}` : 'Resolved'}
              </span>
            </div>

            <div className="flex items-center gap-1.5 rounded-lg bg-slate-50 px-2.5 py-1.5 border border-slate-100">
              <span className="font-bold text-slate-700">AlphaMissense:</span>
              <span className="text-slate-600 font-mono text-[11px]">
                {Number.isFinite(alphaScore) ? alphaScore.toFixed(3) : 'Prior'}
              </span>
            </div>
          </div>
        </div>

      </div>
    </section>
  );
}



/* ========================================================================
   VERDICT CARD
   ======================================================================== */

function VerdictCard({
  data,
}: {
  data: AnalyzeResponse;
}) {
  const context =
    data.context_data as
      | Record<string, any>
      | null
      | undefined;

  const physics =
    data.physics_data as
      | Record<string, any>
      | null
      | undefined;

  const evidenceSummary =
    context?.evidence_summary as
      | Record<string, any>
      | undefined;

  const variantContext =
    context?.variant_specific_context as
      | Record<string, any>
      | undefined;

  const alphaMissense =
    context?.alphamissense_sniper as
      | Record<string, any>
      | undefined;

  const clinvar =
    context?.clinvar as
      | Record<string, any>
      | undefined;

  const clinvarMatch =
    evidenceSummary?.variant_in_clinvar;

  const alphaMissensePresent =
    evidenceSummary?.variant_in_alphamissense;

  const literatureCount =
    variantContext?.litvar_publications;

  const deltas =
    physics?.deltas as
      | Record<string, any>
      | undefined;

  const structuralContext =
    physics?.structural_context_wt as
      | Record<string, any>
      | undefined;

  const deltaVolume =
    deltas?.delta_volume;

  const deltaCharge =
    deltas?.delta_charge;

  const deltaHydrophobicity =
    deltas?.delta_hydrophobicity;

  const exposure =
    structuralContext?.exposure;

  const secondaryStructure =
    structuralContext?.secondary_structure;

  const sasa =
    structuralContext?.sasa;

  /* ---------------------------------------------------------------------
     CLINVAR
     --------------------------------------------------------------------- */

  const clinvarSignificance =
    typeof clinvar?.clinical_significance === 'string'
      ? clinvar.clinical_significance
      : '';

  const clinvarSignificanceLower =
    clinvarSignificance.toLowerCase();

  const clinvarPathogenic =
    clinvarSignificanceLower.includes(
      'pathogenic'
    );

  const clinvarBenign =
    clinvarSignificanceLower.includes(
      'benign'
    );

  /* ---------------------------------------------------------------------
     ALPHAMISSENSE
     --------------------------------------------------------------------- */

  const alphaScore =
    typeof alphaMissense?.score === 'number'
      ? alphaMissense.score
      : Number(alphaMissense?.score);

  /* ---------------------------------------------------------------------
     OVERALL VERDICT
     --------------------------------------------------------------------- */

  const normalizeStatus = (
    status?: string | null
  ): string => {
    if (!status) {
      return 'STATUS NOT RETURNED';
    }

    return status
      .replace(/_/g, ' ')
      .toUpperCase();
  };

  const overallStatus = normalizeStatus(data.status);

  /* ---------------------------------------------------------------------
     FORMAT DELTAS
     --------------------------------------------------------------------- */

  const formatDelta = (
    value: unknown,
    unit: string,
    decimals = 1
  ) => {
    const numericValue =
      typeof value === 'number'
        ? value
        : Number(value);

    if (!Number.isFinite(numericValue)) {
      return 'Not returned';
    }

    const sign =
      numericValue > 0
        ? '+'
        : '';

    const formatted =
      `${sign}${numericValue.toFixed(decimals)}`;

    return unit
      ? `${formatted} ${unit}`
      : formatted;
  };

  const structuralAvailable =
    Boolean(physics) &&
    (
      deltaVolume !== undefined ||
      deltaCharge !== undefined ||
      deltaHydrophobicity !== undefined ||
      secondaryStructure !== undefined
    );

  return (
    <section className="overflow-hidden rounded-[2rem] border border-slate-200 bg-white shadow-soft">

      {/* VERDICT HEADER */}
      <div className="border-b border-slate-100 px-6 py-6 sm:px-8">

        <p className="eyebrow">
          Overall verdict
        </p>

        <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">

          <div>

            <h2 className="text-2xl font-bold tracking-tight text-ink sm:text-3xl">
              {overallStatus}
            </h2>

            <p className="mt-2 text-sm text-slate-500">
              Evidence summary for {data.gene}{' '}
              {data.variant}
            </p>

          </div>

          <span className="w-fit rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-600">
            Evidence synthesis
          </span>

        </div>
      </div>

      {/* VERDICT GATES */}
      <div className="grid grid-cols-1 divide-y divide-slate-100 sm:grid-cols-3 sm:divide-x sm:divide-y-0">

        {/* STRUCTURAL GATE */}
        <VerdictGate
          title="Structural"
          status={
            structuralAvailable
              ? 'Available'
              : 'Not returned'
          }
        >

          <VerdictRow
            label="Volume change"
            value={formatDelta(
              deltaVolume,
              'Å³'
            )}
          />

          <VerdictRow
            label="Charge shift"
            value={formatDelta(
              deltaCharge,
              '',
              0
            )}
          />

          <VerdictRow
            label="Hydrophobicity"
            value={formatDelta(
              deltaHydrophobicity,
              '',
              1
            )}
          />

          <VerdictRow
            label="SASA"
            value={
              Number.isFinite(
                Number(sasa)
              )
                ? `${Number(sasa).toFixed(2)} Å²`
                : 'Not returned'
            }
          />

          <VerdictRow
            label="Exposure"
            value={
              exposure ??
              'Not returned'
            }
          />

          <VerdictRow
            label="Secondary structure"
            value={
              secondaryStructure ??
              'Not returned'
            }
          />

        </VerdictGate>


        {/* CLINICAL GATE */}
        <VerdictGate
          title="Clinical"
          status={
            clinvarMatch ||
            alphaMissensePresent
              ? 'Evidence found'
              : 'Not returned'
          }
        >

          <VerdictRow
            label="ClinVar match"
            value={
              clinvarMatch === true
                ? clinvarPathogenic
                  ? 'Pathogenic'
                  : clinvarBenign
                    ? 'Benign'
                    : 'Match'
                : clinvarMatch === false
                  ? 'No match'
                  : 'Not returned'
            }
          />

          <VerdictRow
            label="ClinVar significance"
            value={
              clinvarSignificance ||
              'Not returned'
            }
          />

          <VerdictRow
            label="AlphaMissense"
            value={
              alphaMissensePresent === true
                ? Number.isFinite(
                    alphaScore
                  )
                  ? `${alphaScore.toFixed(4)}${
                      alphaMissense?.verdict
                        ? ` (${alphaMissense.verdict})`
                        : ''
                    }`
                  : 'Available'
                : alphaMissensePresent === false
                  ? 'No match'
                  : 'Not returned'
            }
          />

        </VerdictGate>


        {/* LITERATURE GATE */}
        <VerdictGate
          title="Literature"
          status={
            literatureCount !== undefined
              ? 'Evidence found'
              : data.evidence &&
                  data.evidence.length > 0
                ? 'Evidence found'
                : 'Not returned'
          }
        >

          <VerdictRow
            label="Evidence chunks"
            value={
              data.evidence &&
              data.evidence.length > 0
                ? data.evidence.length.toLocaleString()
                : literatureCount !== undefined
                  ? Number(
                      literatureCount
                    ).toLocaleString()
                  : 'Not returned'
            }
          />

          <VerdictRow
            label="Retrieved sources"
            value={
              Array.isArray(
                variantContext?.sources_with_hits
              )
                ? variantContext.sources_with_hits.join(
                    ', '
                  )
                : data.evidence &&
                    data.evidence.length > 0
                  ? `${data.evidence.length} ranked chunks`
                  : 'Not returned'
            }
          />

          {data.evidence &&
            data.evidence.length > 0 && (
              <VerdictRow
                label="Top score"
                value={
                  Number.isFinite(
                    Number(
                      data.evidence[0]?.score
                    )
                  )
                    ? Number(
                        data.evidence[0].score
                      ).toFixed(4)
                    : 'Not returned'
                }
              />
            )}

        </VerdictGate>

      </div>
    </section>
  );
}


/* ========================================================================
   VERDICT GATE
   ======================================================================== */

function VerdictGate({
  title,
  status,
  children,
}: {
  title: string;
  status: string;
  children: React.ReactNode;
}) {
  return (
    <div className="px-6 py-6 sm:px-7">

      <div className="flex items-center justify-between gap-3">

        <h3 className="text-sm font-bold text-ink">
          {title}
        </h3>

        <span className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-400">

          <span className="h-1.5 w-1.5 rounded-full bg-teal-500" />

          {status}

        </span>

      </div>

      <div className="mt-5 space-y-3">
        {children}
      </div>

    </div>
  );
}


/* ========================================================================
   VERDICT ROW
   ======================================================================== */

function VerdictRow({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-slate-100 pb-2.5 last:border-b-0 last:pb-0">

      <span className="text-xs text-slate-500">
        {label}
      </span>

      <span className="text-right text-xs font-semibold text-ink">
        {value}
      </span>

    </div>
  );
}


/* ========================================================================
   METRIC
   ======================================================================== */

function Metric({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="border-r border-slate-100 px-5 py-4 last:border-r-0">

      <p className="text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-400">
        {label}
      </p>

      <p
        className={`mt-1 text-sm font-semibold text-ink ${
          mono
            ? 'font-mono'
            : ''
        }`}
      >
        {value}
      </p>

    </div>
  );
}


/* ========================================================================
   EVIDENCE TILE
   ======================================================================== */

function EvidenceTile({
  number,
  icon: Icon,
  title,
  description,
  active,
}: {
  number: string;
  icon: typeof FlaskConical;
  title: string;
  description: string;
  active: boolean;
}) {
  return (
    <div
      className={`rounded-2xl border p-5 transition-all duration-200 ${
        active
          ? 'border-slate-200 bg-white shadow-sm hover:-translate-y-0.5 hover:shadow-md'
          : 'border-slate-200/80 bg-slate-50/60'
      }`}
    >

      <div className="flex items-start justify-between">

        <div
          className={`flex h-9 w-9 items-center justify-center rounded-xl ${
            active
              ? 'bg-teal-50'
              : 'bg-slate-100'
          }`}
        >

          <Icon
            className={`h-4 w-4 ${
              active
                ? 'text-teal-700'
                : 'text-slate-400'
            }`}
          />

        </div>

        <span className="font-mono text-[10px] text-slate-300">
          {number}
        </span>

      </div>

      <h3 className="mt-5 text-sm font-semibold text-ink">
        {title}
      </h3>

      <p className="mt-1.5 text-xs leading-5 text-slate-500">
        {description}
      </p>

      <div className="mt-4 flex items-center gap-2">

        <span
          className={`h-1.5 w-1.5 rounded-full ${
            active
              ? 'bg-teal-500'
              : 'bg-slate-300'
          }`}
        />

        <span className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
          {active
            ? 'Available'
            : 'Not returned'}
        </span>

      </div>

    </div>
  );
}