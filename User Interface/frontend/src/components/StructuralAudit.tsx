import {
  Activity,
  ArrowDown,
  ArrowUp,
  Minus,
  ShieldCheck,
} from 'lucide-react';

interface StructuralAuditProps {
  physicsData?: Record<string, unknown> | null;
}

type ComparisonObject = Record<string, unknown>;

type StabilityAudit = {
  salt_bridges_lost?: unknown[];
  salt_bridges_gained?: unknown[];
  disulfides_lost?: unknown[];
  disulfides_gained?: unknown[];
  h_bonds_lost_est?: unknown;
  h_bonds_gained_est?: unknown;
  backbone_strain?: unknown;
};

function isObject(value: unknown): value is ComparisonObject {
  return (
    typeof value === 'object' &&
    value !== null &&
    !Array.isArray(value)
  );
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—';

  if (typeof value === 'number') {
    return Number.isInteger(value)
      ? value.toString()
      : value.toFixed(3);
  }

  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No';
  }

  if (Array.isArray(value)) {
    return value.length === 0 ? 'None' : `${value.length} item(s)`;
  }

  return String(value);
}

function deltaTone(value: unknown) {
  if (typeof value !== 'number' || value === 0) {
    return 'text-slate-500';
  }

  return value > 0 ? 'text-teal-700' : 'text-amber-700';
}

function DeltaIndicator({ value }: { value: unknown }) {
  if (typeof value !== 'number' || value === 0) {
    return <Minus className="h-3 w-3" />;
  }

  return value > 0 ? (
    <ArrowUp className="h-3 w-3" />
  ) : (
    <ArrowDown className="h-3 w-3" />
  );
}

function MetricCard({
  label,
  value,
  sublabel,
}: {
  label: string;
  value: unknown;
  sublabel?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
      <p className="text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-400">
        {label}
      </p>

      <p className="mt-2 font-mono text-xl font-semibold tracking-tight text-ink">
        {formatValue(value)}
      </p>

      {sublabel && (
        <p className="mt-1 text-[10px] leading-4 text-slate-400">
          {sublabel}
        </p>
      )}
    </div>
  );
}

function ComparisonTable({
  comparison,
}: {
  comparison: ComparisonObject;
}) {
  const rows = Object.entries(comparison);

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[620px] border-collapse text-left">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50/70">
            <th className="px-5 py-3 text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-400">
              Property
            </th>
            <th className="px-5 py-3 text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-400">
              Wild type
            </th>
            <th className="px-5 py-3 text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-400">
              Mutant
            </th>
            <th className="px-5 py-3 text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-400">
              Δ
            </th>
          </tr>
        </thead>

        <tbody>
          {rows.map(([key, value]) => {
            const nested = isObject(value);
            const wt = nested ? value.wt : undefined;
            const mut = nested ? value.mut : undefined;
            const delta = nested ? value.delta : undefined;

            return (
              <tr
                key={key}
                className="border-b border-slate-100 last:border-0 hover:bg-slate-50/70"
              >
                <td className="px-5 py-3.5 text-xs font-medium capitalize text-slate-700">
                  {key.replace(/_/g, ' ')}
                </td>

                <td className="px-5 py-3.5 font-mono text-xs text-slate-600">
                  {nested ? formatValue(wt) : formatValue(value)}
                </td>

                <td className="px-5 py-3.5 font-mono text-xs text-slate-600">
                  {nested ? formatValue(mut) : '—'}
                </td>

                <td
                  className={`px-5 py-3.5 font-mono text-xs font-semibold ${deltaTone(
                    delta
                  )}`}
                >
                  <span className="inline-flex items-center gap-1">
                    {nested && <DeltaIndicator value={delta} />}
                    {nested ? formatValue(delta) : '—'}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function StabilityAudit({ audit }: { audit: StabilityAudit }) {
  const lostSalt = audit.salt_bridges_lost?.length ?? 0;
  const gainedSalt = audit.salt_bridges_gained?.length ?? 0;
  const lostDisulfide = audit.disulfides_lost?.length ?? 0;
  const gainedDisulfide = audit.disulfides_gained?.length ?? 0;

  return (
    <div className="border-t border-slate-200 bg-slate-50/60 px-5 py-5 sm:px-6">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-teal-50">
          <ShieldCheck className="h-4 w-4 text-teal-700" />
        </div>

        <div>
          <h4 className="text-sm font-semibold text-ink">
            Stability audit
          </h4>
          <p className="mt-0.5 text-xs leading-5 text-slate-500">
            Interaction and backbone checks returned by the pipeline.
          </p>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <AuditStat label="Salt bridges lost" value={lostSalt} />
        <AuditStat label="Salt bridges gained" value={gainedSalt} />
        <AuditStat label="Disulfides lost" value={lostDisulfide} />
        <AuditStat label="Disulfides gained" value={gainedDisulfide} />
      </div>

      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <AuditStat
          label="H-bonds lost"
          value={audit.h_bonds_lost_est}
        />
        <AuditStat
          label="H-bonds gained"
          value={audit.h_bonds_gained_est}
        />
        <AuditStat
          label="Backbone strain"
          value={audit.backbone_strain}
        />
      </div>
    </div>
  );
}

function AuditStat({
  label,
  value,
}: {
  label: string;
  value: unknown;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
      <p className="text-[9px] font-semibold uppercase tracking-[0.1em] text-slate-400">
        {label}
      </p>
      <p className="mt-1.5 font-mono text-sm font-semibold text-ink">
        {formatValue(value)}
      </p>
    </div>
  );
}

export default function StructuralAudit({
  physicsData,
}: StructuralAuditProps) {
  if (!physicsData || Object.keys(physicsData).length === 0) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white shadow-soft">
        <div className="flex items-center gap-3 px-5 py-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-100">
            <Activity className="h-4 w-4 text-slate-500" />
          </div>

          <div>
            <h3 className="text-sm font-semibold text-ink">
              Structural physics audit
            </h3>
            <p className="mt-0.5 text-xs text-slate-500">
              No structural metrics were returned.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const comparison = isObject(physicsData.comparison_view)
    ? physicsData.comparison_view
    : null;

  const stability = isObject(physicsData.stability_audit)
    ? (physicsData.stability_audit as StabilityAudit)
    : null;

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft">

      {/* HEADER */}
      <div className="border-b border-slate-200 px-5 py-5 sm:px-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-teal-50">
              <Activity className="h-4 w-4 text-teal-700" />
            </div>

            <div>
              <div className="flex items-center gap-2">
                <p className="eyebrow">Structural layer</p>
              </div>

              <h3 className="mt-1 text-base font-semibold tracking-tight text-ink">
                Physics audit
              </h3>

              <p className="mt-1 max-w-xl text-xs leading-5 text-slate-500">
                Comparative residue properties and structural context
                returned by the active pipeline.
              </p>
            </div>
          </div>

          {typeof physicsData.variant === 'string' && (
            <span className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 font-mono text-[10px] font-medium text-slate-600">
              {physicsData.variant}
            </span>
          )}
        </div>
      </div>

      {/* KEY METRICS */}
      <div className="p-5 sm:p-6">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetricCard
            label="Residue"
            value={
              comparison && isObject(comparison.residue)
                ? comparison.residue.wt
                : undefined
            }
            sublabel="Wild-type"
          />

          <MetricCard
            label="Volume Δ"
            value={
              comparison && isObject(comparison.volume)
                ? comparison.volume.delta
                : undefined
            }
            sublabel="Residue volume"
          />

          <MetricCard
            label="Hydrophobicity Δ"
            value={
              comparison && isObject(comparison.hydrophobicity)
                ? comparison.hydrophobicity.delta
                : undefined
            }
            sublabel="Hydrophobicity"
          />

          <MetricCard
            label="Charge Δ"
            value={
              comparison && isObject(comparison.charge)
                ? comparison.charge.delta
                : undefined
            }
            sublabel="Net charge"
          />
        </div>

        {/* COMPARISON */}
        {comparison && (
          <div className="mt-5 overflow-hidden rounded-xl border border-slate-200">
            <div className="border-b border-slate-200 px-5 py-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h4 className="text-sm font-semibold text-ink">
                    Wild-type vs mutant
                  </h4>

                  <p className="mt-1 text-xs text-slate-500">
                    Direct comparison of returned residue properties.
                  </p>
                </div>

                <span className="hidden rounded-full bg-slate-100 px-2 py-1 text-[9px] font-medium uppercase tracking-wider text-slate-500 sm:block">
                  Computed values
                </span>
              </div>
            </div>

            <ComparisonTable comparison={comparison} />
          </div>
        )}

        {/* STRUCTURAL CONTEXT */}
        {isObject(physicsData.structural_context_wt) && (
          <div className="mt-5">
            <div className="mb-3">
              <h4 className="text-sm font-semibold text-ink">
                Structural context
              </h4>
              <p className="mt-1 text-xs text-slate-500">
                Baseline wild-type structural measurements.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {Object.entries(physicsData.structural_context_wt).map(
                ([key, value]) => (
                  <MetricCard
                    key={key}
                    label={key.replace(/_/g, ' ')}
                    value={value}
                  />
                )
              )}
            </div>
          </div>
        )}
      </div>

      {/* STABILITY */}
      {stability && <StabilityAudit audit={stability} />}
    </div>
  );
}