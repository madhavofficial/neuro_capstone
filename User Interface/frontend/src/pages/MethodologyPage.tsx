import {
  ArrowRight,
  Database,
  FlaskConical,
  GitBranch,
  Search,
  ShieldCheck,
} from 'lucide-react';

const stages = [
  {
    number: '01',
    icon: Database,
    title: 'Structure & Variant Resolution',
    short: 'Resolve',
    description:
      'Target sequences and canonical coordinates are retrieved. The system prioritizes high-confidence baseline models and performs in silico mutagenesis to construct the variant geometry.',
  },
  {
    number: '02',
    icon: FlaskConical,
    title: 'Physics & Structural Audit',
    short: 'Audit',
    description:
      'Geometric and chemical perturbations are evaluated through structural measurements including SASA, residue volume, charge, and hydrophobicity.',
  },
  {
    number: '03',
    icon: ShieldCheck,
    title: 'Biomedical Context Verification',
    short: 'Verify',
    description:
      'The baseline status of the gene and variant is checked against established biomedical sources and pathogenicity registries.',
  },
  {
    number: '04',
    icon: Search,
    title: 'Literature Retrieval',
    short: 'Retrieve',
    description:
      'Relevant biomedical literature is retrieved from the available evidence pipeline, with contextual ranking used to surface potentially useful literature chunks.',
  },
];

export default function MethodologyPage() {
  return (
    <div className="space-y-12 pb-8">

      {/* PAGE HEADER */}
      <section className="max-w-4xl">
        <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-teal-100 bg-teal-50 px-3 py-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-teal-600" />
          <span className="text-[9px] font-semibold uppercase tracking-[0.16em] text-teal-700">
            System architecture
          </span>
        </div>

        <h1 className="text-4xl font-semibold tracking-[-0.035em] text-ink sm:text-5xl">
          Hybrid-Audit
          <span className="block text-teal-700">
            methodology.
          </span>
        </h1>

        <p className="mt-5 max-w-3xl text-sm leading-7 text-slate-500 sm:text-base">
          The framework addresses the structure–function gap in
          computational biomedical prediction by separating deterministic
          structural analysis from contextual biomedical evidence.
        </p>
      </section>

      {/* PIPELINE */}
      <section>
        <div className="mb-6 flex items-end justify-between gap-4">
          <div>
            <p className="eyebrow">Pipeline architecture</p>
            <h2 className="mt-1 text-xl font-semibold tracking-tight text-ink">
              Four evidence layers
            </h2>
          </div>

          <span className="hidden text-[9px] font-medium uppercase tracking-[0.12em] text-slate-400 sm:block">
            Resolve → Audit → Verify → Retrieve
          </span>
        </div>

        {/* desktop connector */}
        <div className="relative hidden lg:block">
          <div className="absolute left-[8%] right-[8%] top-14 h-px bg-slate-200" />

          <div className="grid grid-cols-4 gap-4">
            {stages.map((stage) => {
              const Icon = stage.icon;

              return (
                <article
                  key={stage.number}
                  className="group relative rounded-2xl border border-slate-200 bg-white p-5 shadow-soft transition-all duration-200 hover:-translate-y-1 hover:border-teal-200 hover:shadow-lg"
                >
                  <div className="relative z-10 mb-7 flex items-center justify-between">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-teal-100 bg-teal-50">
                      <Icon className="h-4 w-4 text-teal-700" />
                    </div>

                    <span className="font-mono text-[10px] font-medium text-slate-300">
                      {stage.number}
                    </span>
                  </div>

                  <p className="text-[9px] font-semibold uppercase tracking-[0.14em] text-teal-700">
                    {stage.short}
                  </p>

                  <h3 className="mt-2 text-sm font-semibold leading-5 text-ink">
                    {stage.title}
                  </h3>

                  <p className="mt-3 text-xs leading-5 text-slate-500">
                    {stage.description}
                  </p>
                </article>
              );
            })}
          </div>
        </div>

        {/* mobile/tablet */}
        <div className="grid gap-4 lg:hidden">
          {stages.map((stage, index) => {
            const Icon = stage.icon;

            return (
              <article
                key={stage.number}
                className="relative rounded-2xl border border-slate-200 bg-white p-5 shadow-soft"
              >
                <div className="flex gap-4">
                  <div className="flex shrink-0 flex-col items-center">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-teal-50">
                      <Icon className="h-4 w-4 text-teal-700" />
                    </div>

                    {index < stages.length - 1 && (
                      <div className="mt-2 h-full min-h-8 w-px bg-slate-200" />
                    )}
                  </div>

                  <div className="pb-2">
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-[10px] text-slate-300">
                        {stage.number}
                      </span>

                      <span className="text-[9px] font-semibold uppercase tracking-[0.14em] text-teal-700">
                        {stage.short}
                      </span>
                    </div>

                    <h3 className="mt-2 text-sm font-semibold text-ink">
                      {stage.title}
                    </h3>

                    <p className="mt-2 text-xs leading-5 text-slate-500">
                      {stage.description}
                    </p>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      {/* PRINCIPLE */}
      <section className="grid gap-5 lg:grid-cols-[0.8fr_1.2fr]">

        <div className="rounded-2xl bg-ink p-7 text-white shadow-soft">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/10">
            <GitBranch className="h-5 w-5 text-teal-300" />
          </div>

          <p className="mt-8 text-[9px] font-semibold uppercase tracking-[0.16em] text-teal-300">
            Design principle
          </p>

          <h2 className="mt-2 text-2xl font-semibold tracking-tight">
            Separate evidence from inference.
          </h2>

          <p className="mt-4 text-sm leading-6 text-slate-300">
            The interface is designed as an evidence viewer. Returned
            backend objects are displayed without inventing unsupported
            scientific conclusions.
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-7 shadow-soft">
          <p className="eyebrow">Execution model</p>

          <div className="mt-6 space-y-5">
            {[
              ['Input', 'Gene symbol + missense variant'],
              ['Processing', 'Structure, physics, context and literature'],
              ['Output', 'Structured evidence returned by the pipeline'],
            ].map(([label, value], index) => (
              <div
                key={label}
                className="flex items-start gap-4"
              >
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-slate-100 font-mono text-[9px] font-semibold text-slate-500">
                  0{index + 1}
                </div>

                <div>
                  <p className="text-xs font-semibold text-ink">
                    {label}
                  </p>

                  <p className="mt-1 text-xs leading-5 text-slate-500">
                    {value}
                  </p>
                </div>

                {index < 2 && (
                  <ArrowRight className="ml-auto mt-1 hidden h-3.5 w-3.5 text-slate-300 sm:block" />
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* LIMITATIONS */}
      <section className="rounded-2xl border border-amber-200 bg-amber-50/60 p-6 sm:p-7">
        <div className="flex items-start gap-4">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white">
            <ShieldCheck className="h-4 w-4 text-amber-700" />
          </div>

          <div>
            <p className="text-[9px] font-semibold uppercase tracking-[0.15em] text-amber-700">
              Development status
            </p>

            <h3 className="mt-1 text-sm font-semibold text-amber-950">
              Current runtime boundaries
            </h3>

            <p className="mt-2 max-w-4xl text-xs leading-6 text-amber-900/75">
              The interface displays information explicitly returned by
              the active backend execution. Planned conceptual layers
              that are not currently integrated into the runtime are
              intentionally not presented as completed results.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}