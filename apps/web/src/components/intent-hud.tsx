import type { IntentUpdated, VisualIntent } from '@glia/api-client'
import { useSessionStore } from '@/stores/session'

const FIELD_ROWS: ReadonlyArray<{
  label: string
  value: (intent: VisualIntent) => string | string[]
}> = [
  { label: 'Subject', value: (intent) => intent.subject },
  { label: 'Mood', value: (intent) => intent.moods },
  { label: 'Style', value: (intent) => intent.styles },
  { label: 'Palette', value: (intent) => intent.palette },
  { label: 'Composition', value: (intent) => intent.composition },
  { label: 'Medium', value: (intent) => intent.medium },
  { label: 'Era', value: (intent) => intent.era },
]

const SOURCE_LABELS: Record<IntentUpdated['source'], string> = {
  pioneer: 'live',
  fixture: 'demo',
  local: 'local',
}

function formatValue(value: string | string[]): string {
  const text = Array.isArray(value) ? value.filter(Boolean).join(', ') : value.trim()
  return text || '—'
}

export function IntentHud() {
  const update = useSessionStore((state) => state.intentUpdate)
  const ideasUpdate = useSessionStore((state) => state.ideasUpdate)
  const sourceLabel = update ? SOURCE_LABELS[update.source] : 'waiting'

  return (
    <aside className="intent-hud" aria-label="Fastino visual direction" aria-live="polite">
      <header className="intent-hud-header">
        <div>
          <p className="intent-hud-kicker">Fastino</p>
          <h2>Visual direction</h2>
        </div>
        <span className="intent-hud-status" data-live={update?.source === 'pioneer'}>
          <span aria-hidden="true" />
          {sourceLabel}
        </span>
      </header>

      {update ? (
        <>
          <dl className="intent-hud-fields">
            {FIELD_ROWS.map((field) => (
              <div key={field.label}>
                <dt>{field.label}</dt>
                <dd>{formatValue(field.value(update.intent))}</dd>
              </div>
            ))}
          </dl>
          <p className="intent-hud-gate">
            Cala gate <strong>{update.should_discover ? 'open' : 'held'}</strong>
          </p>
          {ideasUpdate ? (
            <p className="intent-hud-ideas">
              OpenAI <strong>{ideasUpdate.source === 'openai' ? 'ready' : 'local fallback'}</strong>
              <span>{ideasUpdate.keywords.slice(0, 3).join(' · ')}</span>
            </p>
          ) : update.should_discover ? (
            <p className="intent-hud-ideas">OpenAI shaping directions…</p>
          ) : null}
        </>
      ) : (
        <p className="intent-hud-empty">
          Finish a thought and its visual ingredients will appear here.
        </p>
      )}
    </aside>
  )
}
