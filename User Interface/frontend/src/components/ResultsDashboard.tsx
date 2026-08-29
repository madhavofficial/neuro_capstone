import React from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  FileCode2,
  FlaskConical,
  ShieldCheck,
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

      {/* OVERALL VERDICT */}
      <VerdictCard data={data} />

      {/* CLINICAL INTERPRETATION */}
      {data.clinical_narrative && (
        <ClinicalNarrativeCard
          narrative={data.clinical_narrative}
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
   CLINICAL NARRATIVE
   ======================================================================== */

function ClinicalNarrativeCard({
  narrative,
  gene,
  variant,
}: {
  narrative: string;
  gene: string;
  variant: string;
}) {
  return (
    <section className="overflow-hidden rounded-2xl border border-teal-100 bg-white shadow-soft">

      <div className="border-b border-teal-100 bg-teal-50/50 px-5 py-5 sm:px-6">

        <div className="flex items-start gap-3">

          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-teal-100">
            <ShieldCheck className="h-4 w-4 text-teal-700" />
          </div>

          <div>

            <p className="eyebrow text-teal-700">
              Clinical synthesis
            </p>

            <h3 className="mt-1 text-base font-semibold tracking-tight text-ink">
              Clinical Interpretation & Evidence Synthesis
            </h3>

            <p className="mt-1 text-xs leading-5 text-slate-500">
              Human-readable interpretation for {gene} {variant},
              linking the evidence returned by the active pipeline.
            </p>

          </div>

        </div>

      </div>

      <div className="px-5 py-6 sm:px-6">

        <div className="rounded-xl border border-slate-100 bg-slate-50/60 px-4 py-4">

          <p className="whitespace-pre-line text-sm leading-7 text-slate-700">
            {narrative}
          </p>

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