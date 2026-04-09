import { useMemo, useState } from 'react'
import { DataBrowser } from './components/DataBrowser'
import { DataTable } from './components/DataTable'
import { ConversationPanel } from './components/ConversationPanel'
import { useEligibleRecords } from './hooks/useEligibleRecords'
import { useVoiceSession } from './hooks/useVoiceSession'
import type { DataView } from './types/patient'

export default function App() {
  const [view, setView] = useState<DataView>('patients')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const {
    eligible,
    promotionRows,
    scenarioRows,
    counts,
    loading,
    error,
    lastLoaded,
    reload,
  } = useEligibleRecords()

  const voice = useVoiceSession()

  const selected = useMemo(
    () => eligible.find((r) => r.record_id === selectedId) ?? null,
    [eligible, selectedId],
  )

  const handleHeaderConnect = () => {
    if (voice.status === 'live' || voice.status === 'connecting') {
      voice.finalize()
    } else {
      void voice.connect(selectedId).catch(() => {})
    }
  }

  return (
    <div className="flex h-full min-h-screen flex-col bg-dg-background text-dg-platinum">
      <header className="flex shrink-0 items-center justify-between border-b border-dg-border bg-dg-almost-black px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-dg-gradient-start to-dg-gradient-end">
            <svg className="h-4 w-4 text-dg-almost-black" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.114 5.636a9 9 0 010 12.728M16.463 8.288a5.25 5.25 0 010 7.424M6.75 8.25l4.72-4.72a.75.75 0 011.28.53v15.88a.75.75 0 01-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.01 9.01 0 012.25 12c0-.83.112-1.633.322-2.396C2.806 8.756 3.63 8.25 4.51 8.25H6.75z" />
            </svg>
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-dg-text">
              Patient Connect
            </h1>
            <p className="text-xs text-dg-muted">
              AI-powered drug recommendation calls
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={handleHeaderConnect}
          disabled={voice.status === 'connecting'}
          className="rounded-lg bg-gradient-to-r from-dg-gradient-start to-dg-gradient-end px-4 py-2 text-sm font-medium text-dg-almost-black shadow-md shadow-dg-primary/20 transition hover:brightness-110 disabled:opacity-50"
        >
          {voice.status === 'live' || voice.status === 'connecting'
            ? 'Disconnect'
            : 'Connect'}
        </button>
      </header>

      {error && (
        <div className="shrink-0 border-b border-dg-danger/30 bg-dg-danger/10 px-6 py-2 text-center text-xs text-dg-danger">
          {error} — is the Python API running on port 8000?
        </div>
      )}

      {loading && (
        <div className="shrink-0 border-b border-dg-border px-6 py-2 text-center text-xs text-dg-muted">
          Loading eligible records…
        </div>
      )}

      <div className="flex min-h-0 min-h-[calc(100vh-5.5rem)] flex-1">
        <DataBrowser active={view} onSelect={setView} counts={counts} />
        <DataTable
          view={view}
          eligible={eligible}
          promotionRows={promotionRows}
          scenarioRows={scenarioRows}
          selectedId={selectedId}
          onSelectRecord={setSelectedId}
        />
        <ConversationPanel
          selected={selected}
          status={voice.status}
          messages={voice.messages}
          lastError={voice.lastError}
          onConnect={() => void voice.connect(selectedId).catch(() => {})}
          onFinalize={voice.finalize}
        />
      </div>

      <footer className="flex shrink-0 items-center justify-center gap-8 border-t border-dg-border bg-dg-almost-black py-3 text-[10px] text-dg-pebble">
        <span className="tabular-nums">
          Last sync:{' '}
          {lastLoaded
            ? lastLoaded.toLocaleTimeString(undefined, {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
              })
            : '—'}
        </span>
        <button
          type="button"
          onClick={() => void reload()}
          className="text-dg-primary/80 hover:text-dg-primary"
        >
          Refresh data
        </button>
        <span className="flex items-center gap-6">
          <span className="bg-gradient-to-r from-dg-gradient-start to-dg-gradient-end bg-clip-text text-transparent font-medium">Deepgram</span>
          <span>AWS</span>
          <span>SageMaker + Bedrock</span>
        </span>
      </footer>
    </div>
  )
}
