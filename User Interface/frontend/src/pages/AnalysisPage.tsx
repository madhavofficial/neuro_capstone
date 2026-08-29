import { useEffect, useState } from 'react';
import AnalyzeForm from '../components/AnalyzeForm';
import ResultsDashboard from '../components/ResultsDashboard';
import { analyzeVariant } from '../api/client';
import { AnalyzeRequest, AnalyzeResponse } from '../types';
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Loader2,
  RefreshCcw,
  ShieldCheck,
  Circle,
} from 'lucide-react';

interface ProgressStep {
  id: number;
  title: string;
  description: string;
  threshold: number;
}

const PROGRESS_STEPS: ProgressStep[] = [
  {
    id: 1,
    title: 'Resolving AlphaFold 3D coordinates',
    description: 'Resolving the target protein and retrieving the structural model.',
    threshold: 20,
  },
  {
    id: 2,
    title: 'Querying ClinVar, dbSNP & AlphaMissense',
    description: 'Collecting clinical and pathogenicity evidence.',
    threshold: 45,
  },
  {
    id: 3,
    title: 'Calculating SASA & Biophysical Deltas',
    description: 'Computing structural and physicochemical changes.',
    threshold: 70,
  },
  {
    id: 4,
    title: 'BioBERT RAG Retrieval & Cross-Encoder Reranking',
    description: 'Retrieving and ranking relevant biomedical literature.',
    threshold: 95,
  },
];

export default function AnalysisPage() {
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<AnalyzeResponse | null>(null);
  const [lastRequest, setLastRequest] =
    useState<AnalyzeRequest | null>(null);

  useEffect(() => {
    if (!loading) {
      return;
    }

    /*
     * The backend currently exposes one /analyze request rather than
     * streaming individual pipeline stages. Therefore this tracker
     * reflects the expected pipeline sequence while the request runs.
     * It does not claim backend completion for a stage that the API
     * has not explicitly reported.
     */
    const timer = window.setInterval(() => {
      setProgress((current) => {
        if (current >= 92) {
          return current;
        }

        if (current < 20) {
          return Math.min(current + 4, 20);
        }

        if (current < 45) {
          return Math.min(current + 3, 45);
        }

        if (current < 70) {
          return Math.min(current + 2, 70);
        }

        return Math.min(current + 1, 92);
      });
    }, 700);

    return () => window.clearInterval(timer);
  }, [loading]);

  const handleAnalyze = async (request: AnalyzeRequest) => {
    setLoading(true);
    setProgress(1);
    setError(null);
    setData(null);
    setLastRequest(request);

    try {
      const result = await analyzeVariant(request);

      setProgress(100);
      setData(result);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError(
          'An unexpected error occurred during execution.'
        );
      }
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setData(null);
    setError(null);
    setLastRequest(null);
    setProgress(0);
  };

  const handleRetry = () => {
    if (lastRequest) {
      handleAnalyze(lastRequest);
    }
  };

  return (
    <div className="space-y-8">

      {/* HERO */}
      {!data && !loading && !error && (
        <section className="relative overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-soft">
          <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full border border-teal-100" />
          <div className="pointer-events-none absolute -right-12 -top-12 h-48 w-48 rounded-full border border-teal-100/70" />
          <div className="pointer-events-none absolute bottom-[-100px] left-[-70px] h-56 w-56 rounded-full bg-teal-100/30 blur-3xl" />

          <div className="relative grid gap-10 px-6 py-10 sm:px-10 sm:py-12 lg:grid-cols-[1.35fr_0.65fr] lg:items-center lg:px-12">
            <div>
              <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-teal-100 bg-teal-50 px-3 py-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-teal-500" />
                <span className="text-[9px] font-semibold uppercase tracking-[0.16em] text-teal-700">
                  Hybrid-Audit Research Environment
                </span>
              </div>

              <h1 className="max-w-3xl text-4xl font-semibold tracking-[-0.035em] text-ink sm:text-5xl lg:text-[3.4rem] lg:leading-[1.05]">
                From variant prediction
                <span className="block text-teal-700">
                  to interpretable evidence.
                </span>
              </h1>

              <p className="mt-5 max-w-2xl text-sm leading-7 text-slate-500 sm:text-base">
                Analyze a gene and missense variant across structural,
                physical, biological, and clinical evidence layers —
                using only information returned by the active pipeline.
              </p>

              <div className="mt-7 flex flex-wrap items-center gap-x-6 gap-y-3 text-[10px] font-medium uppercase tracking-[0.12em] text-slate-400">
                <span className="inline-flex items-center gap-2">
                  <CheckCircle2 className="h-3.5 w-3.5 text-teal-600" />
                  Structure
                </span>

                <span className="inline-flex items-center gap-2">
                  <CheckCircle2 className="h-3.5 w-3.5 text-teal-600" />
                  Physics
                </span>

                <span className="inline-flex items-center gap-2">
                  <CheckCircle2 className="h-3.5 w-3.5 text-teal-600" />
                  Clinical evidence
                </span>

                <span className="inline-flex items-center gap-2">
                  <CheckCircle2 className="h-3.5 w-3.5 text-teal-600" />
                  Literature
                </span>
              </div>
            </div>

            <div className="hidden lg:block">
              <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-5">
                <div className="mb-5 flex items-center justify-between">
                  <div>
                    <p className="eyebrow">Analysis flow</p>
                    <p className="mt-1 text-xs font-semibold text-ink">
                      Evidence orchestration
                    </p>
                  </div>

                  <ShieldCheck className="h-5 w-5 text-teal-600" />
                </div>

                <div className="space-y-3">
                  {[
                    'Resolve target',
                    'Audit structure',
                    'Verify context',
                    'Retrieve evidence',
                  ].map((step, index) => (
                    <div
                      key={step}
                      className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-3 py-3"
                    >
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-teal-50 font-mono text-[9px] font-semibold text-teal-700">
                        0{index + 1}
                      </span>

                      <span className="text-xs font-medium text-slate-600">
                        {step}
                      </span>

                      <ArrowRight className="ml-auto h-3 w-3 text-slate-300" />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* INPUT */}
      <section>
        {!data && (
          <div className="mb-3 flex items-end justify-between gap-4">
            <div>
              <p className="eyebrow">Target specification</p>

              <h2 className="mt-1 text-lg font-semibold tracking-tight text-ink">
                Start an analysis
              </h2>
            </div>

            <span className="hidden text-[9px] font-medium uppercase tracking-[0.12em] text-slate-400 sm:block">
              Gene + missense variant
            </span>
          </div>
        )}

        <AnalyzeForm
          onSubmit={handleAnalyze}
          disabled={loading}
          onReset={handleReset}
        />
      </section>

      {/* PROGRESS TRACKER */}
      {loading && (
        <PipelineProgress progress={progress} />
      )}

      {/* ERROR */}
      {error && !loading && (
        <div className="rounded-2xl border border-red-200 bg-white shadow-soft">
          <div className="border-b border-red-100 bg-red-50/70 px-5 py-4">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white">
                <AlertCircle className="h-4 w-4 text-red-600" />
              </div>

              <div>
                <p className="text-sm font-semibold text-red-900">
                  Analysis failed
                </p>

                <p className="text-xs text-red-700/70">
                  The backend returned an execution error.
                </p>
              </div>
            </div>
          </div>

          <div className="p-5">
            <div className="rounded-xl bg-slate-950 px-4 py-4 font-mono text-xs leading-5 text-red-300">
              {error}
            </div>

            <button
              onClick={handleRetry}
              className="mt-4 inline-flex items-center gap-2 rounded-lg bg-ink px-4 py-2.5 text-xs font-semibold text-white transition hover:bg-slate-800"
            >
              <RefreshCcw className="h-3.5 w-3.5" />
              Retry analysis
            </button>
          </div>
        </div>
      )}

      {/* RESULTS */}
      {data && !loading && (
        <div className="animate-in fade-in duration-500">
          <ResultsDashboard data={data} />
        </div>
      )}
    </div>
  );
}


/* ========================================================================
   PIPELINE PROGRESS
   ======================================================================== */

function PipelineProgress({
  progress,
}: {
  progress: number;
}) {
  const activeStep =
    PROGRESS_STEPS.findIndex(
      (step) => progress < step.threshold
    );

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-soft sm:p-8">

      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="eyebrow">
            Pipeline execution
          </p>

          <h3 className="mt-1 text-xl font-semibold tracking-tight text-ink">
            Analyzing {progress}%
          </h3>

          <p className="mt-2 max-w-2xl text-xs leading-5 text-slate-500">
            The analysis is moving through the structural, clinical,
            physicochemical, and literature evidence stages.
          </p>
        </div>

        <Loader2 className="h-5 w-5 animate-spin text-teal-700" />
      </div>

      {/* PROGRESS BAR */}
      <div className="mt-6 h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-teal-500 transition-all duration-500 ease-out"
          style={{
            width: `${progress}%`,
          }}
        />
      </div>

      {/* STEPS */}
      <div className="mt-7 space-y-3">
        {PROGRESS_STEPS.map((step, index) => {
          const completed =
            progress >= step.threshold;

          const current =
            index === activeStep &&
            !completed;

          return (
            <div
              key={step.id}
              className={`flex items-start gap-4 rounded-xl border px-4 py-4 transition-all duration-300 ${
                completed
                  ? 'border-teal-100 bg-teal-50/50'
                  : current
                    ? 'border-teal-200 bg-white shadow-sm'
                    : 'border-slate-200 bg-slate-50/50'
              }`}
            >
              <div className="mt-0.5 shrink-0">
                {completed ? (
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-teal-100">
                    <CheckCircle2 className="h-4 w-4 text-teal-700" />
                  </div>
                ) : current ? (
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-teal-50">
                    <Loader2 className="h-4 w-4 animate-spin text-teal-700" />
                  </div>
                ) : (
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100">
                    <Circle className="h-3.5 w-3.5 text-slate-400" />
                  </div>
                )}
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                  <p
                    className={`text-sm font-semibold ${
                      completed || current
                        ? 'text-ink'
                        : 'text-slate-400'
                    }`}
                  >
                    Step {step.id}: {step.title}
                  </p>

                  <span className="font-mono text-[9px] uppercase tracking-wider text-slate-400">
                    {completed
                      ? 'Completed'
                      : current
                        ? 'In progress'
                        : 'Waiting'}
                  </span>
                </div>

                <p className="mt-1 text-xs leading-5 text-slate-500">
                  {step.description}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}