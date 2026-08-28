import React from 'react';
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Database,
  ShieldCheck,
} from 'lucide-react';

interface ClinicalContextProps {
  contextData?: Record<string, unknown> | null;
}

function formatLabel(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function isObject(value: unknown): value is Record<string, unknown> {
  return (
    typeof value === 'object' &&
    value !== null &&
    !Array.isArray(value)
  );
}

function primitiveValue(value: unknown): string {
  if (value === null || value === undefined) return '—';

  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No';
  }

  if (typeof value === 'number') {
    return Number.isInteger(value)
      ? value.toString()
      : value.toFixed(3);
  }

  return String(value);
}

function Value({
  value,
  level = 0,
}: {
  value: unknown;
  level?: number;
}) {
  const [expanded, setExpanded] = React.useState(level < 1);

  if (value === null || value === undefined) {
    return (
      <span className="font-mono text-xs text-slate-400">
        —
      </span>
    );
  }

  if (
    typeof value === 'string' ||
    typeof value === 'number' ||
    typeof value === 'boolean'
  ) {
    return (
      <span className="break-words text-xs leading-5 text-slate-700">
        {primitiveValue(value)}
      </span>
    );
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return (
        <span className="text-xs italic text-slate-400">
          No entries returned
        </span>
      );
    }

    return (
      <div className="mt-1 space-y-1.5">
        {value.map((item, index) => (
          <div
            key={index}
            className="flex items-start gap-2 rounded-lg bg-slate-50 px-3 py-2"
          >
            <span className="mt-0.5 font-mono text-[10px] text-slate-400">
              {String(index + 1).padStart(2, '0')}
            </span>

            <div className="min-w-0 flex-1">
              <Value value={item} level={level + 1} />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (isObject(value)) {
    const entries = Object.entries(value);

    if (entries.length === 0) {
      return (
        <span className="text-xs italic text-slate-400">
          Empty object
        </span>
      );
    }

    return (
      <div className="mt-1">
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="inline-flex items-center gap-1.5 rounded-md px-1.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
        >
          {expanded ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}

          {expanded ? 'Hide details' : `${entries.length} fields`}
        </button>

        {expanded && (
          <div className="mt-2 space-y-2 border-l border-slate-200 pl-3">
            {entries.map(([key, nestedValue]) => (
              <div
                key={key}
                className="grid gap-1 sm:grid-cols-[150px_minmax(0,1fr)] sm:gap-4"
              >
                <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-400">
                  {formatLabel(key)}
                </span>

                <div className="min-w-0">
                  <Value
                    value={nestedValue}
                    level={level + 1}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <span className="text-xs text-slate-700">
      {String(value)}
    </span>
  );
}

function Section({
  title,
  value,
  accent = false,
}: {
  title: string;
  value: unknown;
  accent?: boolean;
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 transition hover:border-slate-300 hover:shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h4 className="text-xs font-semibold tracking-tight text-ink">
          {formatLabel(title)}
        </h4>

        {accent && (
          <span className="inline-flex items-center gap-1 rounded-full bg-teal-50 px-2 py-1 text-[9px] font-semibold uppercase tracking-wider text-teal-700">
            <CheckCircle2 className="h-3 w-3" />
            Verified
          </span>
        )}
      </div>

      <Value value={value} />
    </section>
  );
}

function EvidenceSummary({
  value,
}: {
  value: unknown;
}) {
  if (!isObject(value)) {
    return <Section title="Evidence summary" value={value} />;
  }

  return (
    <section className="rounded-xl border border-teal-100 bg-teal-50/40 p-4">
      <div className="mb-3 flex items-center gap-2">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-white shadow-sm">
          <ShieldCheck className="h-3.5 w-3.5 text-teal-700" />
        </div>

        <div>
          <h4 className="text-xs font-semibold text-ink">
            Evidence summary
          </h4>

          <p className="text-[10px] text-slate-500">
            Consolidated context returned by the pipeline.
          </p>
        </div>
      </div>

      <div className="space-y-2">
        {Object.entries(value).map(([key, nestedValue]) => (
          <div
            key={key}
            className="rounded-lg border border-teal-100 bg-white px-3 py-2.5"
          >
            <p className="mb-1 text-[9px] font-semibold uppercase tracking-[0.1em] text-slate-400">
              {formatLabel(key)}
            </p>

            <Value value={nestedValue} />
          </div>
        ))}
      </div>
    </section>
  );
}

export default function ClinicalContext({
  contextData,
}: ClinicalContextProps) {
  if (!contextData || Object.keys(contextData).length === 0) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white shadow-soft">
        <div className="flex items-center gap-3 px-5 py-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-100">
            <Database className="h-4 w-4 text-slate-500" />
          </div>

          <div>
            <p className="eyebrow">Evidence layer</p>
            <h3 className="mt-1 text-sm font-semibold text-ink">
              Biological & clinical context
            </h3>

            <p className="mt-0.5 text-xs text-slate-500">
              No context data was returned.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const excludedKeys = new Set([
    'literature',
    'evidence',
    'papers',
    'publications',
    'chunks',
  ]);

  const entries = Object.entries(contextData).filter(
    ([key]) => !excludedKeys.has(key.toLowerCase())
  );

  const evidenceSummary = contextData.evidence_summary;

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft">
      {/* HEADER */}
      <div className="border-b border-slate-200 px-5 py-5 sm:px-6">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-teal-50">
            <Database className="h-4 w-4 text-teal-700" />
          </div>

          <div>
            <p className="eyebrow">Evidence layer</p>

            <h3 className="mt-1 text-base font-semibold tracking-tight text-ink">
              Biological & clinical context
            </h3>

            <p className="mt-1 max-w-xl text-xs leading-5 text-slate-500">
              Variant-specific and gene-level evidence returned from
              the active biomedical data sources.
            </p>
          </div>
        </div>
      </div>

      {/* CONTENT */}
      <div className="space-y-3 p-5 sm:p-6">
        {entries.map(([key, value]) => {
          const important =
            key.toLowerCase() === 'clinvar' ||
            key.toLowerCase() === 'alphamissense_sniper';

          return (
            <Section
              key={key}
              title={key}
              value={value}
              accent={important}
            />
          );
        })}

        {evidenceSummary !== undefined && (
          <EvidenceSummary value={evidenceSummary} />
        )}
      </div>
    </div>
  );
}
