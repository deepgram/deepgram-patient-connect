import type { DataView } from '../types/patient'

const views: { id: DataView; label: string; icon: 'table' | 'pill' | 'flow' }[] = [
  { id: 'patients', label: 'patients', icon: 'table' },
  { id: 'promotions', label: 'promotions', icon: 'pill' },
  { id: 'scenarios', label: 'call scenarios', icon: 'flow' },
]

function Icon({
  name,
  className,
}: {
  name: 'table' | 'pill' | 'flow'
  className?: string
}) {
  const cn = className ?? 'h-4 w-4'
  if (name === 'table')
    return (
      <svg className={cn} fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M4 6h16M4 10h16M4 14h16M4 18h16"
        />
      </svg>
    )
  if (name === 'pill')
    return (
      <svg className={cn} fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M19.428 15.428a8 8 0 00-11.314 0L3 20.5V21h.5l5.086-5.086a8 8 0 0011.314 0L21 20.5V21h-.5l-1.072-1.072z"
        />
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M15 9a3 3 0 11-6 0 3 3 0 016 0z"
        />
      </svg>
    )
  return (
    <svg className={cn} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M13 10V3L4 14h7v7l9-11h-7z"
      />
    </svg>
  )
}

export function DataBrowser({
  active,
  onSelect,
  counts,
}: {
  active: DataView
  onSelect: (v: DataView) => void
  counts: Record<DataView, number>
}) {
  return (
    <aside className="flex h-full min-h-0 w-[220px] shrink-0 flex-col border-r border-dg-border bg-dg-almost-black">
      <div className="flex items-center gap-2 border-b border-dg-border px-4 py-3">
        <svg
          className="h-4 w-4 text-dg-primary"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4"
          />
        </svg>
        <span className="text-sm font-medium tracking-tight text-dg-platinum">
          Data Browser
        </span>
      </div>
      <nav className="flex flex-1 flex-col gap-0.5 p-2">
        {views.map((v) => {
          const isActive = active === v.id
          return (
            <button
              key={v.id}
              type="button"
              onClick={() => onSelect(v.id)}
              className={`flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left text-sm transition-colors ${
                isActive
                  ? 'bg-dg-primary/15 text-dg-text ring-1 ring-dg-primary/30'
                  : 'text-dg-muted hover:bg-white/[0.04] hover:text-dg-platinum'
              }`}
            >
              <span className="flex items-center gap-2.5">
                <Icon name={v.icon} className="h-4 w-4 shrink-0 opacity-80" />
                <span className="truncate">{v.label}</span>
              </span>
              <span
                className={`shrink-0 rounded-md px-1.5 py-0.5 text-xs tabular-nums ${
                  isActive ? 'bg-dg-primary/20 text-dg-primary' : 'text-dg-pebble'
                }`}
              >
                {counts[v.id]}
              </span>
            </button>
          )
        })}
      </nav>
    </aside>
  )
}
