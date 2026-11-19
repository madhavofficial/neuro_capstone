import { useLayoutEffect, useMemo, useRef, type RefObject } from "react";
import {
  buildSequenceDiff,
  sequenceDiffSubline,
  type ChainResidue,
  type SequenceDiff as SequenceDiffModel,
} from "../lib/sequenceDiff";

interface SequenceDiffProps {
  pdbContent: string;
  variant?: string;
}

function tickVisibility(residues: ChainResidue[], changeIndex: number | null): boolean[] {
  const show = residues.map(
    (residue, index) => index === 0 || residue.resseq % 10 === 0,
  );

  if (changeIndex !== null && changeIndex >= 0 && changeIndex < residues.length) {
    for (let index = 0; index < show.length; index += 1) {
      if (index !== changeIndex && Math.abs(index - changeIndex) < 4) {
        show[index] = false;
      }
    }
    show[changeIndex] = true;
  }

  return show;
}

function residueLabel(residue: ChainResidue): string {
  return `${residue.resseq}${residue.icode}`;
}

function SequenceRow({
  label,
  residues,
  changeIndex,
  markChange,
  changeRef,
}: {
  label: string;
  residues: ChainResidue[];
  changeIndex: number | null;
  markChange: boolean;
  changeRef?: RefObject<HTMLSpanElement>;
}) {
  return (
    <div className="flex items-center">
      <div className="sticky left-0 z-10 w-24 shrink-0 bg-slate-50 pr-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">
        {label}
      </div>
      <div className="flex" data-testid={markChange ? "sequence-variant" : "sequence-wt"}>
        {residues.map((residue, index) => {
          const changed = markChange && index === changeIndex;
          return (
            <span
              key={`${label}-${index}`}
              ref={changed ? changeRef : undefined}
              data-changed={changed ? "true" : undefined}
              title={
                changed
                  ? `Substituted residue ${residueLabel(residue)}`
                  : `${residue.letter}${residueLabel(residue)}`
              }
              className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-sm font-mono text-[11px] leading-none ${
                changed
                  ? "bg-red-600 font-semibold text-white"
                  : "text-slate-700"
              }`}
            >
              {residue.letter}
            </span>
          );
        })}
      </div>
    </div>
  );
}

export default function SequenceDiff({ pdbContent, variant }: SequenceDiffProps) {
  const diff = useMemo(
    () => buildSequenceDiff(pdbContent, variant ?? ""),
    [pdbContent, variant],
  );
  const scrollerRef = useRef<HTMLDivElement>(null);
  const changeRef = useRef<HTMLSpanElement>(null);
  const subline = sequenceDiffSubline(diff);
  const ticks = tickVisibility(diff.wildType, diff.changeIndex);
  const showVariantRow = diff.variant.length > 0;

  useLayoutEffect(() => {
    const scroller = scrollerRef.current;
    const change = changeRef.current;
    if (!scroller || !change) {
      return;
    }

    const changeRect = change.getBoundingClientRect();
    const scrollerRect = scroller.getBoundingClientRect();
    const delta =
      changeRect.left -
      scrollerRect.left -
      scroller.clientWidth / 2 +
      changeRect.width / 2;
    scroller.scrollLeft += delta;
  }, [diff]);

  return (
    <section className="mt-5 border-t border-slate-200 pt-5" data-testid="sequence-diff">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h4 className="text-sm font-semibold text-ink">1D chain vs wild type</h4>
          {subline && <p className="mt-1 text-xs text-slate-500">{subline}</p>}
        </div>

        {diff.status === "diff" && (
          <span className="inline-flex w-fit items-center gap-2 text-[10px] text-slate-400">
            <span className="h-2.5 w-2.5 rounded-full bg-red-600" />
            Substituted residue
          </span>
        )}
      </div>

      {diff.status === "diff" &&
        diff.wildLetter &&
        diff.mutantLetter &&
        diff.position !== null && (
          <p
            className="mt-3 font-mono text-xs font-semibold text-ink"
            data-testid="sequence-diff-callout"
          >
            {diff.wildLetter}
            {diff.position} to {diff.mutantLetter}
          </p>
        )}

      {diff.notice && (
        <p
          className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800"
          data-testid="sequence-diff-notice"
        >
          {diff.notice}
        </p>
      )}

      {diff.wildType.length > 0 && (
        <div
          ref={scrollerRef}
          tabIndex={0}
          aria-label="Wild-type and variant amino-acid sequences"
          className="mt-4 max-w-full overflow-x-auto rounded-xl border border-slate-200 bg-slate-50 px-3 py-3"
        >
          <div className="min-w-max space-y-1">
            <div className="flex items-end">
              <div className="sticky left-0 z-10 h-4 w-24 shrink-0 bg-slate-50" />
              <div className="flex">
                {diff.wildType.map((residue, index) => (
                  <span
                    key={`tick-${index}`}
                    className={`flex h-4 w-5 shrink-0 items-end justify-center font-mono text-[8px] leading-none ${
                      index === diff.changeIndex
                        ? "font-semibold text-red-600"
                        : "text-slate-400"
                    }`}
                  >
                    {ticks[index] ? residueLabel(residue) : ""}
                  </span>
                ))}
              </div>
            </div>

            <SequenceRow
              label="Wild type"
              residues={diff.wildType}
              changeIndex={diff.changeIndex}
              markChange={false}
            />

            {showVariantRow && (
              <SequenceRow
                label="Variant"
                residues={diff.variant}
                changeIndex={diff.changeIndex}
                markChange
                changeRef={changeRef}
              />
            )}
          </div>
        </div>
      )}

      <SequenceSummary diff={diff} />
    </section>
  );
}

function SequenceSummary({ diff }: { diff: SequenceDiffModel }) {
  if (
    diff.status !== "diff" ||
    !diff.wildLetter ||
    !diff.mutantLetter ||
    diff.position === null
  ) {
    return null;
  }

  const chain = diff.chainId?.trim() ? ` on chain ${diff.chainId}` : "";

  return (
    <p className="sr-only">
      Wild type {diff.wildLetter} at residue {diff.position} is changed to {diff.mutantLetter}
      {chain}.
    </p>
  );
}
