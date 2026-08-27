import React, { useState } from 'react';
import {
  ArrowRight,
  Dna,
  RotateCcw,
  Search,
} from 'lucide-react';
import { AnalyzeRequest } from '../types';

interface AnalyzeFormProps {
  onSubmit: (req: AnalyzeRequest) => void;
  onReset: () => void;
  disabled: boolean;
}

export default function AnalyzeForm({
  onSubmit,
  onReset,
  disabled,
}: AnalyzeFormProps) {
  const [gene, setGene] = useState('');
  const [variant, setVariant] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (gene.trim() && variant.trim()) {
      onSubmit({
        gene: gene.trim(),
        variant: variant.trim(),
      });
    }
  };

  const handleReset = () => {
    setGene('');
    setVariant('');
    onReset();
  };

  const hasInput = Boolean(gene || variant);

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-2xl border border-slate-200 bg-slate-50/80 p-2 shadow-sm"
    >
      <div className="grid grid-cols-1 gap-2 lg:grid-cols-[1fr_1fr_auto]">

        {/* Gene */}
        <div className="group rounded-xl border border-transparent bg-white px-4 py-3 transition-all duration-200 focus-within:border-teal-200 focus-within:shadow-focus">
          <label
            htmlFor="gene"
            className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.13em] text-slate-400"
          >
            <Dna className="h-3.5 w-3.5 text-teal-600" />
            Gene / protein
          </label>

          <input
            id="gene"
            type="text"
            value={gene}
            onChange={(e) => setGene(e.target.value)}
            disabled={disabled}
            placeholder="SNCA"
            className="mt-1.5 w-full border-0 bg-transparent p-0 font-mono text-sm font-medium text-ink outline-none placeholder:text-slate-300 disabled:opacity-50"
            required
          />
        </div>

        {/* Variant */}
        <div className="group rounded-xl border border-transparent bg-white px-4 py-3 transition-all duration-200 focus-within:border-teal-200 focus-within:shadow-focus">
          <label
            htmlFor="variant"
            className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.13em] text-slate-400"
          >
            <Search className="h-3.5 w-3.5 text-teal-600" />
            Missense variant
          </label>

          <input
            id="variant"
            type="text"
            value={variant}
            onChange={(e) => setVariant(e.target.value)}
            disabled={disabled}
            placeholder="A53T"
            className="mt-1.5 w-full border-0 bg-transparent p-0 font-mono text-sm font-medium text-ink outline-none placeholder:text-slate-300 disabled:opacity-50"
            required
          />
        </div>

        {/* Actions */}
        <div className="flex gap-2 lg:flex-col xl:flex-row">
          {hasInput && (
            <button
              type="button"
              onClick={handleReset}
              disabled={disabled}
              className="flex items-center justify-center rounded-xl border border-slate-200 bg-white px-4 py-3 text-slate-500 transition-all hover:bg-slate-50 hover:text-ink disabled:opacity-50"
              aria-label="Reset"
            >
              <RotateCcw className="h-4 w-4" />
            </button>
          )}

          <button
            type="submit"
            disabled={disabled || !gene.trim() || !variant.trim()}
            className="group flex min-h-[48px] flex-1 items-center justify-center gap-2 rounded-xl bg-ink px-6 text-sm font-semibold text-white shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:bg-slate-800 hover:shadow-md disabled:translate-y-0 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <span>Analyze variant</span>
            <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" />
          </button>
        </div>
      </div>
    </form>
  );
}