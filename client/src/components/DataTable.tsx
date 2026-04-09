import { useMemo, useState } from 'react'
import type {
  DataView,
  PatientRecord,
  PromotionRow,
  ScenarioRow,
} from '../types/patient'

function SearchIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      aria-hidden
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
      />
    </svg>
  )
}

export function DataTable({
  view,
  eligible,
  promotionRows,
  scenarioRows,
  selectedId,
  onSelectRecord,
}: {
  view: DataView
  eligible: PatientRecord[]
  promotionRows: PromotionRow[]
  scenarioRows: ScenarioRow[]
  selectedId: string | null
  onSelectRecord: (id: string | null) => void
}) {
  const [q, setQ] = useState('')

  const title =
    view === 'patients'
      ? 'Patients'
      : view === 'promotions'
        ? 'Promotions'
        : 'Call scenarios'

  const filteredPatients = useMemo(() => {
    if (view !== 'patients') return []
    const s = q.trim().toLowerCase()
    if (!s) return eligible
    return eligible.filter((r) => {
      const hay = [
        r.record_id,
        r.patient.first_name,
        r.patient.last_name,
        r.clinical.primary_condition,
        r.promotion.drug_name,
        r.call.scenario_label,
      ]
        .join(' ')
        .toLowerCase()
      return hay.includes(s)
    })
  }, [eligible, q, view])

  const filteredPromotions = useMemo(() => {
    if (view !== 'promotions') return []
    const s = q.trim().toLowerCase()
    if (!s) return promotionRows
    return promotionRows.filter((p) =>
      `${p.drug_name} ${p.manufacturer} ${p.promotion_type}`
        .toLowerCase()
        .includes(s),
    )
  }, [promotionRows, q, view])

  const filteredScenarios = useMemo(() => {
    if (view !== 'scenarios') return []
    const s = q.trim().toLowerCase()
    if (!s) return scenarioRows
    return scenarioRows.filter((x) =>
      `${x.scenario_type} ${x.scenario_label}`.toLowerCase().includes(s),
    )
  }, [scenarioRows, q, view])

  const count =
    view === 'patients'
      ? filteredPatients.length
      : view === 'promotions'
        ? filteredPromotions.length
        : filteredScenarios.length

  return (
    <section className="flex min-h-0 min-w-0 flex-1 flex-col border-r border-dg-border bg-dg-almost-black">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-dg-border px-4 py-3">
        <div>
          <h2 className="text-sm font-medium text-dg-text">{title}</h2>
          <p className="text-xs text-dg-muted">{count} records</p>
        </div>
        <label className="relative flex items-center">
          <SearchIcon className="pointer-events-none absolute left-2.5 h-4 w-4 text-dg-muted" />
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search…"
            className="w-48 rounded-lg border border-dg-border bg-dg-charcoal py-1.5 pl-8 pr-2 text-xs text-dg-platinum placeholder:text-dg-pebble focus:border-dg-primary/50 focus:outline-none focus:ring-1 focus:ring-dg-primary/40"
          />
        </label>
      </header>

      <div className="min-h-0 flex-1 overflow-auto">
        {view === 'patients' && (
          <table className="w-full min-w-[640px] border-collapse text-left text-xs">
            <thead className="sticky top-0 z-10 bg-dg-charcoal text-[10px] font-semibold uppercase tracking-wider text-dg-muted">
              <tr>
                <th className="px-4 py-2">Record ID</th>
                <th className="px-4 py-2">Patient</th>
                <th className="px-4 py-2">State</th>
                <th className="px-4 py-2">Condition</th>
                <th className="px-4 py-2">Drug</th>
                <th className="px-4 py-2">Scheduled</th>
                <th className="px-4 py-2">Scenario</th>
              </tr>
            </thead>
            <tbody className="text-dg-platinum">
              {filteredPatients.map((r) => {
                const active = selectedId === r.record_id
                return (
                  <tr
                    key={r.record_id}
                    onClick={() =>
                      onSelectRecord(active ? null : r.record_id)
                    }
                    className={`cursor-pointer border-t border-dg-border/50 transition-colors hover:bg-white/[0.03] ${
                      active ? 'bg-dg-primary/8' : ''
                    }`}
                  >
                    <td className="whitespace-nowrap px-4 py-2 font-mono text-[11px] text-dg-primary/80">
                      {r.record_id}
                    </td>
                    <td className="px-4 py-2">
                      {r.patient.first_name} {r.patient.last_name}
                    </td>
                    <td className="px-4 py-2 text-dg-muted">
                      {r.patient.state}
                    </td>
                    <td className="max-w-[140px] truncate px-4 py-2">
                      {r.clinical.primary_condition}
                    </td>
                    <td className="max-w-[160px] truncate px-4 py-2">
                      {r.promotion.drug_name}
                    </td>
                    <td className="whitespace-nowrap px-4 py-2 text-dg-muted">
                      {r.call.scheduled_datetime.replace('T', ' ')}
                    </td>
                    <td className="max-w-[200px] truncate px-4 py-2 text-dg-muted">
                      {r.call.scenario_label}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}

        {view === 'promotions' && (
          <table className="w-full min-w-[520px] border-collapse text-left text-xs">
            <thead className="sticky top-0 z-10 bg-dg-charcoal text-[10px] font-semibold uppercase tracking-wider text-dg-muted">
              <tr>
                <th className="px-4 py-2">Drug</th>
                <th className="px-4 py-2">Manufacturer</th>
                <th className="px-4 py-2">Program type</th>
                <th className="px-4 py-2">Eligible patients</th>
              </tr>
            </thead>
            <tbody className="text-dg-platinum">
              {filteredPromotions.map((p) => (
                <tr
                  key={`${p.drug_name}-${p.promotion_type}`}
                  className="border-t border-dg-border/50"
                >
                  <td className="px-4 py-2">{p.drug_name}</td>
                  <td className="px-4 py-2 text-dg-muted">{p.manufacturer}</td>
                  <td className="px-4 py-2 text-dg-muted">{p.promotion_type}</td>
                  <td className="px-4 py-2 tabular-nums text-dg-primary/80">
                    {p.eligible_patients}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {view === 'scenarios' && (
          <table className="w-full min-w-[480px] border-collapse text-left text-xs">
            <thead className="sticky top-0 z-10 bg-dg-charcoal text-[10px] font-semibold uppercase tracking-wider text-dg-muted">
              <tr>
                <th className="px-4 py-2">Scenario type</th>
                <th className="px-4 py-2">Label</th>
                <th className="px-4 py-2">Count</th>
              </tr>
            </thead>
            <tbody className="text-dg-platinum">
              {filteredScenarios.map((s) => (
                <tr key={s.scenario_type} className="border-t border-dg-border/50">
                  <td className="px-4 py-2 font-mono text-[11px] text-dg-muted">
                    {s.scenario_type}
                  </td>
                  <td className="px-4 py-2">{s.scenario_label}</td>
                  <td className="px-4 py-2 tabular-nums text-dg-primary/80">
                    {s.count}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <footer className="shrink-0 border-t border-dg-border px-4 py-2 text-[10px] text-dg-pebble">
        Viewing {count} records · Patient Connect dataset
      </footer>
    </section>
  )
}
