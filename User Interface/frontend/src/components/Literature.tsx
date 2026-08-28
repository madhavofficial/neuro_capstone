import {
  BookOpen,
  ExternalLink,
  FileText,
  Search,
} from 'lucide-react';

interface LiteratureProps {
  contextData?: Record<string, unknown> | null;
}

type LiteratureItem = Record<string, unknown>;

function isObject(value: unknown): value is LiteratureItem {
  return (
    typeof value === 'object' &&
    value !== null &&
    !Array.isArray(value)
  );
}

function getText(
  obj: LiteratureItem,
  keys: string[],
  fallback: string
): string {
  for (const key of keys) {
    const value = obj[key];

    if (
      typeof value === 'string' &&
      value.trim().length > 0
    ) {
      return value;
    }

    if (
      typeof value === 'number' ||
      typeof value === 'boolean'
    ) {
      return String(value);
    }
  }

  return fallback;
}

export default function Literature({
  contextData,
}: LiteratureProps) {
  if (!contextData) return null;

  const possibleKeys = [
    'literature',
    'evidence',
    'papers',
    'publications',
    'chunks',
  ];

  let literatureArray: unknown[] = [];
  let sourceKey = '';

  for (const key of possibleKeys) {
    if (Array.isArray(contextData[key])) {
      literatureArray = contextData[key] as unknown[];
      sourceKey = key;
      break;
    }
  }

  if (literatureArray.length === 0) {
    return (
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft">
        <div className="flex items-start gap-3 border-b border-slate-200 px-5 py-5 sm:px-6">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-100">
            <BookOpen className="h-4 w-4 text-slate-500" />
          </div>

          <div>
            <p className="eyebrow">Evidence layer</p>

            <h3 className="mt-1 text-base font-semibold tracking-tight text-ink">
              Literature evidence
            </h3>

            <p className="mt-1 text-xs leading-5 text-slate-500">
              No structured literature evidence was returned.
            </p>
          </div>
        </div>

        <div className="px-5 py-8 text-center sm:px-6">
          <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-slate-50">
            <Search className="h-4 w-4 text-slate-400" />
          </div>

          <p className="mt-3 text-xs text-slate-500">
            The current backend response contains no literature array.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft">
      {/* HEADER */}
      <div className="border-b border-slate-200 px-5 py-5 sm:px-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-teal-50">
              <BookOpen className="h-4 w-4 text-teal-700" />
            </div>

            <div>
              <p className="eyebrow">Evidence layer</p>

              <h3 className="mt-1 text-base font-semibold tracking-tight text-ink">
                Literature evidence
              </h3>

              <p className="mt-1 text-xs leading-5 text-slate-500">
                Retrieved biomedical evidence associated with the analysis.
              </p>
            </div>
          </div>

          <span className="shrink-0 rounded-full bg-slate-100 px-2.5 py-1 font-mono text-[10px] font-semibold text-slate-500">
            {literatureArray.length} {literatureArray.length === 1 ? 'item' : 'items'}
          </span>
        </div>
      </div>

      {/* RESULTS */}
      <div className="divide-y divide-slate-100">
        {literatureArray.map((item, index) => {
          if (!isObject(item)) {
            return (
              <div
                key={index}
                className="px-5 py-5 sm:px-6"
              >
                <p className="text-xs text-slate-600">
                  {String(item)}
                </p>
              </div>
            );
          }

          const title = getText(
            item,
            ['title', 'name'],
            'Untitled document'
          );

          const snippet = getText(
            item,
            ['text', 'abstract', 'chunk', 'snippet'],
            'No excerpt available.'
          );

          const pmid =
            item.pmid ??
            item.PMID ??
            item.pubmed_id ??
            null;

          const score =
            item.score ??
            item.relevance ??
            null;

          const url =
            typeof item.url === 'string'
              ? item.url
              : typeof item.link === 'string'
                ? item.link
                : pmid
                  ? `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`
                  : null;

          return (
            <article
              key={index}
              className="group px-5 py-5 transition-colors hover:bg-slate-50/60 sm:px-6"
            >
              <div className="flex items-start gap-3">
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 transition-colors group-hover:bg-white">
                  <FileText className="h-3.5 w-3.5 text-slate-500" />
                </div>

                <div className="min-w-0 flex-1">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <h4 className="text-sm font-semibold leading-5 text-ink">
                      {title}
                    </h4>

                    {typeof score === 'number' && (
                      <span className="shrink-0 rounded-md border border-slate-200 bg-white px-2 py-1 font-mono text-[9px] text-slate-500">
                        score {score.toFixed(4)}
                      </span>
                    )}
                  </div>

                  <p className="mt-2 line-clamp-5 text-xs leading-5 text-slate-600">
                    {snippet}
                  </p>

                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    {pmid !== null && pmid !== undefined && (
                      <span className="rounded-md bg-slate-100 px-2 py-1 font-mono text-[9px] font-medium text-slate-500">
                        PMID {String(pmid)}
                      </span>
                    )}

                    {url && (
                      <a
                        href={url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1.5 rounded-md bg-teal-50 px-2.5 py-1.5 text-[10px] font-semibold text-teal-700 transition-colors hover:bg-teal-100"
                      >
                        Open source
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </div>
                </div>
              </div>
            </article>
          );
        })}
      </div>

      {/* FOOTER */}
      {sourceKey && (
        <div className="border-t border-slate-200 bg-slate-50/60 px-5 py-3 sm:px-6">
          <p className="font-mono text-[9px] uppercase tracking-[0.12em] text-slate-400">
            Source field: {sourceKey}
          </p>
        </div>
      )}
    </div>
  );
}