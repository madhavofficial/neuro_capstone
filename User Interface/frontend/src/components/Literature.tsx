import {
  BookOpen,
  ExternalLink,
  FileText,
  Search,
} from 'lucide-react';
import { LiteratureEvidence } from '../types';

interface LiteratureProps {
  contextData?: Record<string, unknown> | null;
  evidence?: LiteratureEvidence[];
}

function HighlightedText({
  text,
  gene,
  variant,
}: {
  text: string;
  gene?: string;
  variant?: string;
}) {
  const keywords = [
    gene,
    variant,
    'pathogenic',
    'mutation',
    'aggregation',
    'misfolding',
    'amyloid',
    'Parkinson',
    'disease',
  ].filter(
    (keyword): keyword is string =>
      Boolean(keyword && keyword.trim())
  );

  if (keywords.length === 0) {
    return <>{text}</>;
  }

  const escapedKeywords = keywords.map(
    (keyword) =>
      keyword.replace(
        /[.*+?^${}()|[\]\\]/g,
        '\\$&'
      )
  );

  const pattern = new RegExp(
    `(${escapedKeywords.join('|')})`,
    'gi'
  );

  const parts = text.split(pattern);

  return (
    <>
      {parts.map((part, index) => {
        const isKeyword = keywords.some(
          (keyword) =>
            part.toLowerCase() ===
            keyword.toLowerCase()
        );

        return isKeyword ? (
          <mark
            key={index}
            className="rounded bg-teal-100 px-0.5 text-teal-900"
          >
            {part}
          </mark>
        ) : (
          <span key={index}>
            {part}
          </span>
        );
      })}
    </>
  );
}

export default function Literature({
  contextData,
  evidence,
}: LiteratureProps) {
  const gene =
    typeof contextData?.gene === 'string'
      ? contextData.gene
      : undefined;

  const variant =
    typeof contextData?.variant === 'string'
      ? contextData.variant
      : undefined;

  /*
   * The backend payload already provides ranked evidence.
   * Keep only the five highest-ranked chunks for the UI.
   */
  const literatureArray =
    Array.isArray(evidence)
      ? [...evidence]
          .sort(
            (a, b) =>
              Number(b.score) -
              Number(a.score)
          )
          .slice(0, 5)
      : [];

  if (literatureArray.length === 0) {
    return (
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft">
        <div className="flex items-start gap-3 border-b border-slate-200 px-5 py-5 sm:px-6">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-100">
            <BookOpen className="h-4 w-4 text-slate-500" />
          </div>

          <div>
            <p className="eyebrow">
              Evidence layer
            </p>

            <h3 className="mt-1 text-base font-semibold tracking-tight text-ink">
              Literature evidence
            </h3>

            <p className="mt-1 text-xs leading-5 text-slate-500">
              No ranked literature evidence was returned.
            </p>
          </div>
        </div>

        <div className="px-5 py-8 text-center sm:px-6">
          <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-slate-50">
            <Search className="h-4 w-4 text-slate-400" />
          </div>

          <p className="mt-3 text-xs text-slate-500">
            The current analysis response contains no
            evidence array.
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
              <p className="eyebrow">
                Evidence layer
              </p>

              <h3 className="mt-1 text-base font-semibold tracking-tight text-ink">
                Literature evidence
              </h3>

              <p className="mt-1 text-xs leading-5 text-slate-500">
                Top cross-encoder ranked biomedical evidence.
              </p>
            </div>
          </div>

          <span className="shrink-0 rounded-full bg-slate-100 px-2.5 py-1 font-mono text-[10px] font-semibold text-slate-500">
            {literatureArray.length} ranked{' '}
            {literatureArray.length === 1
              ? 'item'
              : 'items'}
          </span>
        </div>
      </div>

      {/* RESULTS */}
      <div className="divide-y divide-slate-100">
        {literatureArray.map(
          (item, index) => {
            const title =
              item.title?.trim() ||
              'Untitled document';

            const snippet =
              item.text?.trim() ||
              item.chunk?.trim() ||
              item.abstract?.trim() ||
              item.snippet?.trim() ||
              'No excerpt available.';

            const pmid =
              item.pmid ||
              item.PMID ||
              '';

            const scoreValue =
              item.score !== undefined
                ? Number(item.score)
                : Number(item.relevance);

            const score =
              Number.isFinite(scoreValue)
                ? scoreValue
                : NaN;

            /*
             * Use the actual score-type returned by the backend.
             * Do not claim "Cross-encoder" if the payload says otherwise.
             */
            const scoreType =
              typeof item.score_type === 'string' &&
              item.score_type.trim()
                ? item.score_type.trim()
                : 'Relevance score';

            const displayScoreType =
              scoreType
                .replace(/_/g, ' ')
                .replace(/\b\w/g, (char) =>
                  char.toUpperCase()
                );

            const pubmedUrl =
              pmid
                ? `https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(
                    pmid
                  )}/`
                : null;

            return (
              <article
                key={`${pmid}-${index}`}
                className="group px-5 py-5 transition-colors hover:bg-slate-50/60 sm:px-6"
              >
                <div className="flex items-start gap-3">

                  <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 transition-colors group-hover:bg-white">
                    <FileText className="h-3.5 w-3.5 text-slate-500" />
                  </div>

                  <div className="min-w-0 flex-1">

                    {/* TITLE + SCORE */}
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                      <h4 className="text-sm font-semibold leading-5 text-ink">
                        <HighlightedText
                          text={title}
                          gene={gene}
                          variant={variant}
                        />
                      </h4>

                      {Number.isFinite(score) && (
                        <span className="shrink-0 rounded-md border border-slate-200 bg-white px-2 py-1 font-mono text-[9px] text-slate-500">
                          score {score.toFixed(4)}
                        </span>
                      )}
                    </div>

                    {/* EXCERPT */}
                    <p className="mt-2 line-clamp-5 text-xs leading-5 text-slate-600">
                      <HighlightedText
                        text={snippet}
                        gene={gene}
                        variant={variant}
                      />
                    </p>

                    {/* FOOTER */}
                    <div className="mt-4 flex flex-wrap items-center gap-2">

                      {pmid && (
                        <span className="rounded-md bg-slate-100 px-2 py-1 font-mono text-[9px] font-medium text-slate-500">
                          PMID {pmid}
                        </span>
                      )}

                      {pubmedUrl && (
                        <a
                          href={pubmedUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1.5 rounded-md bg-teal-50 px-2.5 py-1.5 text-[10px] font-semibold text-teal-700 transition-colors hover:bg-teal-100"
                        >
                          View on PubMed
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      )}

                      <span className="rounded-md border border-slate-200 bg-white px-2 py-1 font-mono text-[9px] text-slate-400">
                        {displayScoreType}
                      </span>
                    </div>
                  </div>
                </div>
              </article>
            );
          }
        )}
      </div>

      {/* FOOTER */}
      <div className="border-t border-slate-200 bg-slate-50/60 px-5 py-3 sm:px-6">
        <p className="font-mono text-[9px] uppercase tracking-[0.12em] text-slate-400">
          Showing top {literatureArray.length} reranked evidence{' '}
          {literatureArray.length === 1
            ? 'chunk'
            : 'chunks'}
        </p>
      </div>
    </div>
  );
}
