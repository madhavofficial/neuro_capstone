import {
  Brain,
  CheckCircle2,
  ShieldCheck,
  Target,
} from 'lucide-react';

export default function AboutPage() {
  return (
    <div className="space-y-12 pb-8">

      {/* HEADER */}
      <section className="max-w-4xl">
        <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-teal-100 bg-teal-50 px-3 py-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-teal-600" />
          <span className="text-[9px] font-semibold uppercase tracking-[0.16em] text-teal-700">
            Research project
          </span>
        </div>

        <h1 className="text-4xl font-semibold tracking-[-0.035em] text-ink sm:text-5xl">
          Understanding the
          <span className="block text-teal-700">
            project behind the interface.
          </span>
        </h1>

        <p className="mt-5 max-w-3xl text-sm leading-7 text-slate-500 sm:text-base">
          This platform is the research interface for the capstone
          project{' '}
          <strong className="font-semibold text-slate-700">
            AI for Predicting Protein-Disease Associations in
            Neurodegenerative Disorders.
          </strong>
        </p>
      </section>

      {/* RESEARCH FOCUS */}
      <section className="grid gap-5 lg:grid-cols-[1.15fr_0.85fr]">

        <div className="rounded-2xl border border-slate-200 bg-white p-7 shadow-soft">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-teal-50">
            <Brain className="h-5 w-5 text-teal-700" />
          </div>

          <p className="eyebrow mt-7">
            Research focus
          </p>

          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-ink">
            Making computational predictions easier to interpret.
          </h2>

          <p className="mt-4 text-sm leading-7 text-slate-500">
            Despite the growing volume of computational biological
            data, identifying the mechanisms underlying pathogenic
            variants remains challenging. Prediction scores alone do
            not necessarily provide the structural and biomedical
            context needed to understand why a variant may matter.
          </p>

          <p className="mt-4 text-sm leading-7 text-slate-500">
            The project therefore brings together structural analysis,
            physical property changes, biomedical context, and
            literature evidence into a single evidence-oriented
            workflow.
          </p>
        </div>

        {/* CONDITIONS */}
        <div className="rounded-2xl bg-ink p-7 text-white shadow-soft">
          <p className="text-[9px] font-semibold uppercase tracking-[0.16em] text-teal-300">
            Primary research scope
          </p>

          <h2 className="mt-2 text-2xl font-semibold tracking-tight">
            Neurodegenerative disorders
          </h2>

          <div className="mt-7 space-y-3">
            {[
              "Alzheimer's Disease (AD)",
              "Parkinson's Disease (PD)",
              'Amyotrophic Lateral Sclerosis (ALS)',
            ].map((condition) => (
              <div
                key={condition}
                className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 px-4 py-3"
              >
                <CheckCircle2 className="h-4 w-4 shrink-0 text-teal-300" />

                <span className="text-xs font-medium text-slate-200">
                  {condition}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* INTERFACE PHILOSOPHY */}
      <section className="grid gap-5 md:grid-cols-3">

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-soft">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-100">
            <Target className="h-4 w-4 text-slate-700" />
          </div>

          <h3 className="mt-5 text-sm font-semibold text-ink">
            Evidence first
          </h3>

          <p className="mt-2 text-xs leading-6 text-slate-500">
            The interface prioritizes information returned by the
            active scientific pipeline rather than presenting
            unsupported conclusions.
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-soft">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-teal-50">
            <ShieldCheck className="h-4 w-4 text-teal-700" />
          </div>

          <h3 className="mt-5 text-sm font-semibold text-ink">
            Transparent outputs
          </h3>

          <p className="mt-2 text-xs leading-6 text-slate-500">
            Structural metrics, contextual information, and retrieved
            evidence remain traceable to the objects returned by the
            backend.
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-soft">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-100">
            <Brain className="h-4 w-4 text-slate-700" />
          </div>

          <h3 className="mt-5 text-sm font-semibold text-ink">
            Research-oriented
          </h3>

          <p className="mt-2 text-xs leading-6 text-slate-500">
            The workspace is designed to help researchers inspect
            multiple evidence layers without hiding uncertainty or
            runtime limitations.
          </p>
        </div>
      </section>

      {/* PRINCIPLE */}
      <section className="rounded-2xl border border-teal-200 bg-teal-50/60 p-6 sm:p-8">
        <div className="flex items-start gap-4">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white shadow-sm">
            <ShieldCheck className="h-5 w-5 text-teal-700" />
          </div>

          <div>
            <p className="text-[9px] font-semibold uppercase tracking-[0.16em] text-teal-700">
              Interface philosophy
            </p>

            <h2 className="mt-1 text-lg font-semibold text-teal-950">
              Display what the pipeline actually knows.
            </h2>

            <p className="mt-2 max-w-4xl text-xs leading-6 text-teal-900/70">
              The dashboard is strictly designed as an evidence viewer.
              Returned parameters — from structural availability to
              literature chunks — are presented from the backend
              response rather than fabricated by the interface.
            </p>
          </div>
        </div>
      </section>

    </div>
  );
}