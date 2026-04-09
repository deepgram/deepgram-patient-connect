import type { PatientRecord } from '../types/patient'
import type { ChatMessage, VoiceStatus } from '../hooks/useVoiceSession'

function MicIcon({ className }: { className?: string }) {
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
        strokeWidth={1.25}
        d="M12 14a3 3 0 003-3V5a3 3 0 10-6 0v6a3 3 0 003 3z"
      />
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.25}
        d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4"
      />
    </svg>
  )
}

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
  const label =
    status === 'idle'
      ? 'Disconnected'
      : status === 'connecting'
        ? 'Connecting…'
        : status === 'live'
          ? 'Live'
          : 'Error'

  return (
    <section className="flex min-h-0 w-1/2 min-w-[320px] shrink-0 flex-col bg-dg-almost-black">
      <header className="flex shrink-0 items-center justify-between border-b border-dg-border px-4 py-3">
        <span className="text-sm font-medium text-dg-platinum">Conversation</span>
        <span
          className={`text-xs ${
            status === 'live'
              ? 'text-dg-success'
              : status === 'error'
                ? 'text-dg-danger'
                : 'text-dg-muted'
          }`}
        >
          {label}
        </span>
      </header>

      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-4 px-6 py-8 text-center">
        <div className="rounded-full bg-gradient-to-br from-dg-gradient-start/15 to-dg-gradient-end/15 p-6 ring-1 ring-dg-primary/30">
          <MicIcon className="h-10 w-10 text-dg-primary" />
        </div>
        <div>
          <p className="text-sm font-medium text-dg-platinum">
            {connected ? 'In call…' : 'Ready to assist'}
          </p>
          <p className="mt-1 max-w-xs text-xs leading-relaxed text-dg-muted">
            {connected
              ? 'The agent greets you first, then you can talk. Flux STT + Aura-2 TTS on SageMaker, LLM via Bedrock.'
              : 'Select a patient, then connect. The agent opens the call, then you discuss the program.'}
          </p>
        </div>

        {selected && (
          <div className="w-full max-w-sm rounded-lg border border-dg-border bg-dg-charcoal p-3 text-left text-[11px] text-dg-muted">
            <p className="font-mono text-dg-primary/80">{selected.record_id}</p>
            <p className="mt-1 text-dg-platinum">
              {selected.patient.first_name} {selected.patient.last_name} ·{' '}
              {selected.promotion.drug_name}
            </p>
          </div>
        )}

        <button
          type="button"
          onClick={() => {
            if (connected) {
              onFinalize()
            } else {
              onConnect()
            }
          }}
          disabled={status === 'connecting'}
          className="rounded-lg bg-gradient-to-r from-dg-gradient-start to-dg-gradient-end px-5 py-2 text-sm font-medium text-dg-almost-black shadow-lg shadow-dg-primary/20 transition hover:brightness-110 disabled:opacity-50"
        >
          {connected ? 'Disconnect' : 'Connect'}
        </button>

        {lastError && (
          <p className="max-w-sm text-xs text-dg-danger">{lastError}</p>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-auto border-t border-dg-border px-4 py-3 text-left">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-dg-muted">
          Dialogue
        </p>
        <ul className="space-y-2 text-xs">
          {messages.length === 0 && (
            <li className="text-dg-pebble">No messages yet.</li>
          )}
          {messages.map((m, i) => (
            <li
              key={`${i}-${m.role}-${m.text.slice(0, 32)}`}
              className={`rounded-md px-2 py-1.5 ${
                m.role === 'agent'
                  ? 'border border-dg-primary/20 bg-dg-primary/8 text-dg-platinum'
                  : 'bg-white/[0.06] text-dg-platinum'
              }`}
            >
              <span className="text-[10px] font-semibold uppercase text-dg-muted">
                {m.role === 'agent' ? 'Agent' : 'Patient'}
              </span>
              <p className="mt-0.5 whitespace-pre-wrap">{m.text}</p>
            </li>
          ))}
        </ul>
      </div>

      <div className="shrink-0 border-t border-dg-border px-4 py-3">
        <p className="flex items-start gap-2 text-left text-[11px] leading-snug text-dg-muted">
          <span className="mt-0.5 text-dg-primary" aria-hidden>
            *
          </span>
          Pipecat pipeline: Flux STT{' '}
          <code className="rounded bg-white/[0.06] px-1 font-mono text-[10px] text-dg-muted">
            deepgram-sagemaker
          </code>{' '}
          → Bedrock LLM → Aura-2 TTS on SageMaker.
        </p>
      </div>
    </section>
  )
}
