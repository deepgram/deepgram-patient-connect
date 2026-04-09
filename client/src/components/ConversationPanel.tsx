import { useEffect, useRef } from 'react'
import type { PatientRecord } from '../types/patient'
import type { ChatMessage, VoiceStatus } from '../hooks/useVoiceSession'

export function ConversationPanel({
  selected,
  status,
  messages,
  lastError,
  onConnect,
  onFinalize,
}: {
  selected: PatientRecord | null
  status: VoiceStatus
  messages: ChatMessage[]
  lastError: string | null
  onConnect: () => void
  onFinalize: () => void
}) {
  const connected = status === 'live' || status === 'connecting'
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  return (
    <section className="flex min-h-0 w-[55%] min-w-[400px] shrink-0 flex-col bg-dg-background">
      {/* Header */}
      <header className="flex shrink-0 items-center justify-between border-b border-dg-border bg-dg-almost-black px-5 py-3">
        <div className="flex items-center gap-3">
          <div className={`h-2.5 w-2.5 rounded-full ${
            status === 'live' ? 'bg-dg-success animate-pulse' :
            status === 'connecting' ? 'bg-dg-warning animate-pulse' :
            status === 'error' ? 'bg-dg-danger' : 'bg-dg-pebble'
          }`} />
          <span className="text-sm font-medium text-dg-platinum">
            {status === 'live' ? 'Call Active' :
             status === 'connecting' ? 'Connecting...' :
             status === 'error' ? 'Error' : 'No Active Call'}
          </span>
        </div>
        {connected && (
          <button
            onClick={onFinalize}
            className="rounded-md bg-dg-danger/15 px-3 py-1.5 text-xs font-medium text-dg-danger ring-1 ring-dg-danger/30 transition hover:bg-dg-danger/25"
          >
            End Call
          </button>
        )}
      </header>

      {/* Drug comparison card (stays visible throughout the call) */}
      {selected && (
        <div className="shrink-0 border-b border-dg-border bg-dg-almost-black p-5">
          <div className="mx-auto max-w-lg">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-dg-muted">Drug Comparison</p>
            <div className="grid grid-cols-2 gap-3">
              {/* Current */}
              <div className="rounded-lg border border-dg-border bg-dg-charcoal p-3">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-dg-warning">Current</p>
                <p className="mt-1 text-sm font-medium text-dg-platinum">{selected.clinical.current_medication.name}</p>
                <p className="mt-0.5 text-[11px] text-dg-muted">{selected.clinical.current_medication.drug_class}</p>
                <p className="mt-2 text-[11px] leading-relaxed text-dg-muted">{selected.clinical.current_medication.known_issues}</p>
                <p className="mt-2 text-xs text-dg-pebble">${selected.clinical.current_medication.monthly_cost}/mo</p>
              </div>
              {/* Recommended */}
              <div className="rounded-lg border border-dg-primary/30 bg-dg-primary/5 p-3">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-dg-primary">Recommended</p>
                <p className="mt-1 text-sm font-medium text-dg-platinum">{selected.promotion.drug_name}</p>
                <p className="mt-0.5 text-[11px] text-dg-muted">{selected.promotion.drug_class}</p>
                <ul className="mt-2 space-y-1">
                  {selected.promotion.advantages_over_current.slice(0, 3).map((a, i) => (
                    <li key={i} className="flex gap-1.5 text-[11px] leading-snug text-dg-muted">
                      <span className="mt-0.5 text-dg-success">+</span>{a}
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-[11px] font-medium text-dg-primary">{selected.promotion.benefit_description}</p>
              </div>
            </div>

            {!connected && messages.length === 0 && (
              <button
                onClick={onConnect}
                disabled={status === 'connecting'}
                className="mt-4 w-full rounded-lg bg-gradient-to-r from-dg-gradient-start to-dg-gradient-end py-2.5 text-sm font-semibold text-dg-almost-black shadow-lg shadow-dg-primary/20 transition hover:brightness-110 disabled:opacity-50"
              >
                Start Call with {selected.patient.first_name}
              </button>
            )}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!selected && !connected && messages.length === 0 && (
        <div className="flex flex-1 items-center justify-center px-8">
          <div className="text-center">
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-dg-charcoal ring-1 ring-dg-border">
              <svg className="h-7 w-7 text-dg-pebble" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.25}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0" />
              </svg>
            </div>
            <p className="text-sm text-dg-platinum">Select a patient</p>
            <p className="mt-1 text-xs text-dg-muted">Choose a patient from the table to see their drug comparison and start a call.</p>
          </div>
        </div>
      )}

      {/* Chat messages */}
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto px-5 py-4">
        {messages.length > 0 && (
          <div className="mx-auto max-w-lg space-y-3">
            {messages.map((m, i) => (
              <div
                key={`${i}-${m.role}`}
                className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                  m.role === 'agent'
                    ? 'rounded-bl-md bg-dg-charcoal text-dg-platinum ring-1 ring-dg-border'
                    : 'rounded-br-md bg-dg-primary/15 text-dg-platinum ring-1 ring-dg-primary/25'
                }`}>
                  <p className={`mb-1 text-[10px] font-bold uppercase tracking-wider ${
                    m.role === 'agent' ? 'text-dg-primary' : 'text-dg-secondary'
                  }`}>
                    {m.role === 'agent' ? 'Agent' : 'Patient'}
                  </p>
                  <p className="text-[13px] leading-relaxed">{m.text}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Error */}
      {lastError && (
        <div className="shrink-0 border-t border-dg-danger/30 bg-dg-danger/10 px-5 py-2 text-center text-xs text-dg-danger">
          {lastError}
        </div>
      )}

      {/* Footer */}
      <footer className="shrink-0 border-t border-dg-border bg-dg-almost-black px-5 py-2.5">
        <p className="text-center text-[10px] text-dg-pebble">
          Flux STT + Aura-2 TTS on SageMaker &middot; Bedrock LLM &middot; deepgram-sagemaker
        </p>
      </footer>
    </section>
  )
}
