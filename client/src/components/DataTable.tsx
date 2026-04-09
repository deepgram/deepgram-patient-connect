import { useMemo, useState } from 'react'
import type {
  DataView,
  PatientRecord,
  PromotionRow,
  ScenarioRow,
} from '../types/patient'

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
        r.clinical.current_medication.name,
        r.promotion.drug_name,
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
      `${p.drug_name} ${p.manufacturer}`.toLowerCase().includes(s),
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
    view === 'patients' ? filteredPatients.length
    : view === 'promotions' ? filteredPromotions.length
    : filteredScenarios.length

  return (
    <section className="flex min-h-0 min-w-0 flex-1 flex-col border-r border-dg-border bg-dg-almost-black">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-dg-border px-4 py-3">
        <div>
          <h2 className="text-sm font-medium text-dg-text">
            {view === 'patients' ? 'Patients' : view === 'promotions' ? 'Promotions' : 'Call Scenarios'}
          </h2>
          <p className="text-xs text-dg-muted">{count} records</p>
        </div>
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search..."
          className="w-44 rounded-lg border border-dg-border bg-dg-charcoal py-1.5 px-3 text-xs text-dg-platinum placeholder:text-dg-pebble focus:border-dg-primary/50 focus:outline-none"
        />
      </header>

      <div className="min-h-0 flex-1 overflow-auto">
        {view === 'patients' && (
          <table className="w-full min-w-[600px] border-collapse text-left text-xs">
            <thead className="sticky top-0 z-10 bg-dg-charcoal text-[10px] font-semibold uppercase tracking-wider text-dg-muted">
              <tr>
                <th className="px-3 py-2">Patient</th>
                <th className="px-3 py-2">Condition</th>
                <th className="px-3 py-2">Current Med</th>
                <th className="px-3 py-2 text-dg-primary/60">Recommended</th>
              </tr>
            </thead>
            <tbody className="text-dg-platinum">
              {filteredPatients.map((r) => {
                const active = selectedId === r.record_id
                return (
                  <tr
                    key={r.record_id}
                    onClick={() => onSelectRecord(active ? null : r.record_id)}
                    className={`cursor-pointer border-t border-dg-border/40 transition-colors hover:bg-white/[0.03] ${
                      active ? 'bg-dg-primary/8 ring-1 ring-inset ring-dg-primary/20' : ''
                    }`}
                  >
                    <td className="px-3 py-2.5">
                      <p className="font-medium">{r.patient.first_name} {r.patient.last_name}</p>
                      <p className="text-[10px] text-dg-muted">{r.patient.state_full}</p>
                    </td>
                    <td className="px-3 py-2.5 text-dg-muted">{r.clinical.primary_condition}</td>
                    <td className="px-3 py-2.5">
                      <p>{r.clinical.current_medication.name}</p>
                      <p className="text-[10px] text-dg-warning/70">{r.clinical.current_medication.drug_class}</p>
                    </td>
                    <td className="px-3 py-2.5">
                      <p className="text-dg-primary/90">{r.promotion.drug_name}</p>
                      <p className="text-[10px] text-dg-muted">{r.promotion.drug_class}</p>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}

        {view === 'promotions' && (
          <table className="w-full border-collapse text-left text-xs">
            <thead className="sticky top-0 z-10 bg-dg-charcoal text-[10px] font-semibold uppercase tracking-wider text-dg-muted">
              <tr>
                <th className="px-4 py-2">Drug</th>
                <th className="px-4 py-2">Manufacturer</th>
                <th className="px-4 py-2">Program</th>
                <th className="px-4 py-2">Eligible</th>
              </tr>
            </thead>
            <tbody className="text-dg-platinum">
              {filteredPromotions.map((p) => (
                <tr key={`${p.drug_name}-${p.promotion_type}`} className="border-t border-dg-border/40">
                  <td className="px-4 py-2">{p.drug_name}</td>
                  <td className="px-4 py-2 text-dg-muted">{p.manufacturer}</td>
                  <td className="px-4 py-2 text-dg-muted">{p.promotion_type}</td>
                  <td className="px-4 py-2 text-dg-primary/80">{p.eligible_patients}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {view === 'scenarios' && (
          <table className="w-full border-collapse text-left text-xs">
            <thead className="sticky top-0 z-10 bg-dg-charcoal text-[10px] font-semibold uppercase tracking-wider text-dg-muted">
              <tr>
                <th className="px-4 py-2">Type</th>
                <th className="px-4 py-2">Label</th>
                <th className="px-4 py-2">Count</th>
              </tr>
            </thead>
            <tbody className="text-dg-platinum">
              {filteredScenarios.map((s) => (
                <tr key={s.scenario_type} className="border-t border-dg-border/40">
                  <td className="px-4 py-2 font-mono text-[11px] text-dg-muted">{s.scenario_type}</td>
                  <td className="px-4 py-2">{s.scenario_label}</td>
                  <td className="px-4 py-2 text-dg-primary/80">{s.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  )
}
