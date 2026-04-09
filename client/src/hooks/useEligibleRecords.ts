import { useCallback, useEffect, useMemo, useState } from 'react'
import type {
  PatientRecord,
  PromotionRow,
  ScenarioRow,
} from '../types/patient'

const API = '/api/records'

export function useEligibleRecords() {
  const [eligible, setEligible] = useState<PatientRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastLoaded, setLastLoaded] = useState<Date | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(API)
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        const detail =
          typeof body === 'object' && body && 'detail' in body
            ? String((body as { detail?: string }).detail)
            : res.statusText
        throw new Error(detail || `HTTP ${res.status}`)
      }
      const rows = (await res.json()) as PatientRecord[]
      setEligible(rows)
      setLastLoaded(new Date())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Load failed')
      setEligible([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const promotionRows: PromotionRow[] = useMemo(() => {
    const map = new Map<string, PromotionRow>()
    for (const r of eligible) {
      const key = `${r.promotion.drug_name}|${r.promotion.promotion_type}`
      const existing = map.get(key)
      if (existing) {
        existing.eligible_patients += 1
      } else {
        map.set(key, {
          drug_name: r.promotion.drug_name,
          manufacturer: r.promotion.manufacturer,
          promotion_type: r.promotion.promotion_type,
          eligible_patients: 1,
        })
      }
    }
    return Array.from(map.values()).sort((a, b) =>
      a.drug_name.localeCompare(b.drug_name),
    )
  }, [eligible])

  const scenarioRows: ScenarioRow[] = useMemo(() => {
    const map = new Map<string, ScenarioRow>()
    for (const r of eligible) {
      const key = r.call.scenario_type
      const existing = map.get(key)
      if (existing) {
        existing.count += 1
      } else {
        map.set(key, {
          scenario_type: r.call.scenario_type,
          scenario_label: r.call.scenario_label,
          count: 1,
        })
      }
    }
    return Array.from(map.values()).sort((a, b) => b.count - a.count)
  }, [eligible])

  const counts = useMemo(
    () => ({
      patients: eligible.length,
      promotions: promotionRows.length,
      scenarios: scenarioRows.length,
    }),
    [eligible.length, promotionRows.length, scenarioRows.length],
  )

  return {
    eligible,
    promotionRows,
    scenarioRows,
    counts,
    loading,
    error,
    lastLoaded,
    reload: load,
  }
}
