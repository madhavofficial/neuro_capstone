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
                  <span className="eyebrow">Analysis complete</span>
                </div>

                <h1 className="mt-4 text-3xl font-semibold tracking-[-0.035em] text-ink sm:text-4xl">
                  {data.gene}
                  <span className="mx-2 text-slate-300">/</span>
                  <span className="font-mono text-teal-700">
                    {data.variant}
                  </span>
                </h1>

                <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-500">
                  Evidence returned by the active scientific analysis pipeline,
                  organized into structural, physicochemical, and biological
                  context.
                </p>
              </div>

              <div className="flex shrink-0 items-center gap-2 rounded-xl border border-teal-100 bg-teal-50/70 px-3 py-2">
                <ShieldCheck className="h-4 w-4 text-teal-700" />
                <span className="text-xs font-semibold text-teal-800">
                  Evidence-first output
                </span>
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
                {Object.entries(data.warnings!).map(([key, message]) => (
                  <li key={key}>
                    <span className="font-medium">{message}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>
      )}

      {/* EVIDENCE MAP */}
      <section>
        <div className="mb-4 flex items-end justify-between gap-4">
          <div>
            <p className="eyebrow">Evidence layers</p>
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
          <StructuralAudit physicsData={data.physics_data} />

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
                      PDB coordinate preview
                    </p>
                  </div>
                </div>

                <span className="font-mono text-[10px] uppercase tracking-wider text-slate-400">
                  {data.pdb_content.length.toLocaleString()} chars
                </span>
              </div>

              <div className="p-5 sm:p-6">
                <div className="overflow-hidden rounded-xl bg-[#111827] shadow-inner">
                  <div className="flex items-center gap-1.5 border-b border-white/10 px-4 py-3">
                    <span className="h-2 w-2 rounded-full bg-white/20" />
                    <span className="h-2 w-2 rounded-full bg-white/20" />
                    <span className="h-2 w-2 rounded-full bg-white/20" />
                    <span className="ml-2 font-mono text-[9px] uppercase tracking-widest text-slate-500">
                      PDB preview
                    </span>
                  </div>

                  <pre className="max-h-72 overflow-y-auto whitespace-pre-wrap p-4 font-mono text-[10px] leading-5 text-teal-200">
                    {data.pdb_content.substring(0, 3000)}
                    {data.pdb_content.length > 3000 &&
                      '\n\n... [TRUNCATED FOR PREVIEW] ...'}
                  </pre>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* CONTEXT */}
        <div className="space-y-6">
          <ClinicalContext contextData={data.context_data} />
          <Literature contextData={data.context_data} />
        </div>
      </section>
    </div>
  );
}

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
          mono ? 'font-mono' : ''
        }`}
      >
        {value}
      </p>
    </div>
  );
}

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
            active ? 'bg-teal-50' : 'bg-slate-100'
          }`}
        >
          <Icon
            className={`h-4 w-4 ${
              active ? 'text-teal-700' : 'text-slate-400'
            }`}
          />
        </div>

        <span className="font-mono text-[10px] text-slate-300">
          {number}
        </span>
      </div>

      <h3 className="mt-5 text-sm font-semibold text-ink">{title}</h3>

      <p className="mt-1.5 text-xs leading-5 text-slate-500">
        {description}
      </p>

      <div className="mt-4 flex items-center gap-2">
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            active ? 'bg-teal-500' : 'bg-slate-300'
          }`}
        />
        <span className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
          {active ? 'Available' : 'Not returned'}
        </span>
      </div>
    </div>
  );
}