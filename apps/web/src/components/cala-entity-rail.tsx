import type { Candidate, IdeasUpdated, IntentUpdated } from '@glia/api-client'
import { useEffect, useMemo, useState } from 'react'
import { useSessionStore } from '@/stores/session'

export interface EntitySuggestion {
  name: string
  type: string
}

const MAX_SUGGESTIONS = 3

type RailSource = 'cala' | 'ideas' | 'intent' | 'preview'

export interface EntityRailContent {
  label: string
  source: RailSource
  suggestions: EntitySuggestion[]
}

/**
 * Cala returns entities alongside the same cited answer that feeds Lane A. The rail deliberately
 * derives from those candidates: it never starts another request, never spends another credit,
 * and disappears when Cala has nothing concrete to add.
 */
export function suggestionsFrom(candidates: readonly Candidate[]): EntitySuggestion[] {
  const suggestions = new Map<string, EntitySuggestion>()
  for (const candidate of candidates) {
    const name = candidate.entity_name?.trim()
    const type = candidate.entity_type?.trim()
    if (candidate.lane !== 'cited' || !name || !type) {
      continue
    }
    const key = `${type}:${name}`.toLocaleLowerCase()
    if (!suggestions.has(key)) {
      suggestions.set(key, { name, type })
    }
    if (suggestions.size >= MAX_SUGGESTIONS) {
      break
    }
  }
  return [...suggestions.values()]
}

function uniqueSuggestions(suggestions: readonly EntitySuggestion[]): EntitySuggestion[] {
  const seen = new Set<string>()
  const unique: EntitySuggestion[] = []
  for (const suggestion of suggestions) {
    const name = suggestion.name.trim()
    const type = suggestion.type.trim()
    const key = `${type}:${name}`.toLocaleLowerCase()
    if (!name || !type || seen.has(key)) {
      continue
    }
    seen.add(key)
    unique.push({ name, type })
    if (unique.length >= MAX_SUGGESTIONS) {
      break
    }
  }
  return unique
}

function directionSuggestions(intentUpdate: IntentUpdated | null): EntitySuggestion[] {
  if (!intentUpdate) {
    return []
  }
  const { intent } = intentUpdate
  return uniqueSuggestions([
    { name: intent.subject, type: 'Subject' },
    ...intent.styles.map((name) => ({ name, type: 'Style' })),
    ...(intent.medium ? [{ name: intent.medium, type: 'Medium' }] : []),
    ...intent.moods.map((name) => ({ name, type: 'Mood' })),
  ])
}

/**
 * Pick the most authoritative state currently available without freezing the dev preview.
 *
 * The preview is only an empty-session placeholder. As soon as speech produces an intent it
 * yields to the realtime path; OpenAI's settled visual ideas then replace the fast local intent,
 * and cited Cala entities replace both when the existing billable search completes.
 */
export function entityRailContent({
  candidates,
  ideasUpdate,
  intentUpdate,
  hasTranscript,
  previewSuggestions,
}: {
  candidates: readonly Candidate[]
  ideasUpdate: IdeasUpdated | null
  intentUpdate: IntentUpdated | null
  hasTranscript: boolean
  previewSuggestions?: readonly EntitySuggestion[] | undefined
}): EntityRailContent | null {
  const cala = suggestionsFrom(candidates)
  if (cala.length > 0) {
    return { label: 'Cala · related', source: 'cala', suggestions: cala }
  }

  const ideas = uniqueSuggestions(
    (ideasUpdate?.ideas ?? []).map((name) => ({ name, type: 'Visual idea' })),
  )
  if (ideas.length > 0) {
    return { label: 'Refining · ideas', source: 'ideas', suggestions: ideas }
  }

  const direction = directionSuggestions(intentUpdate)
  if (direction.length > 0) {
    return { label: 'Listening · direction', source: 'intent', suggestions: direction }
  }

  const preview = uniqueSuggestions(previewSuggestions ?? [])
  if (!hasTranscript && preview.length > 0) {
    return { label: 'Demo · related', source: 'preview', suggestions: preview }
  }
  return null
}

interface CalaEntityRailProps {
  previewSuggestions?: readonly EntitySuggestion[] | undefined
}

export function CalaEntityRail({ previewSuggestions }: CalaEntityRailProps) {
  const candidates = useSessionStore((state) => state.candidates)
  const generated = useSessionStore((state) => state.generation)
  const ideasUpdate = useSessionStore((state) => state.ideasUpdate)
  const intentUpdate = useSessionStore((state) => state.intentUpdate)
  const hasTranscript = useSessionStore((state) => Boolean(state.transcript.trim()))
  const content = useMemo(
    () =>
      entityRailContent({
        candidates,
        ideasUpdate,
        intentUpdate,
        hasTranscript,
        previewSuggestions,
      }),
    [candidates, hasTranscript, ideasUpdate, intentUpdate, previewSuggestions],
  )
  const suggestions = content?.suggestions ?? []
  const signature = suggestions
    .map((suggestion) => `${suggestion.type}:${suggestion.name}`)
    .join('|')
  const [entered, setEntered] = useState(false)

  useEffect(() => {
    setEntered(false)
    if (!signature) {
      return
    }
    const frame = requestAnimationFrame(() => setEntered(true))
    return () => cancelAnimationFrame(frame)
  }, [signature])

  if (generated || !content || suggestions.length === 0) {
    return null
  }

  return (
    <aside
      aria-label="Cala related references"
      aria-live="polite"
      data-source={content.source}
      className={`pointer-events-none fixed right-3 bottom-[calc(var(--rail-space)+146px)] left-3 z-40 flex justify-center transition-[opacity,transform] duration-200 ease-[cubic-bezier(0.23,1,0.32,1)] motion-reduce:translate-y-0 motion-reduce:transition-opacity md:right-[330px] md:bottom-[calc(var(--rail-space)+96px)] md:left-[30vw] ${
        entered ? 'translate-y-0 opacity-100' : 'translate-y-2 opacity-0'
      }`}
    >
      <div className="flex min-w-0 max-w-full items-center gap-2 rounded-full border border-black/7 bg-white/88 px-2.5 py-2 shadow-[0_8px_28px_rgb(17_17_17/0.08)] backdrop-blur-md">
        <p className="m-0 shrink-0 pl-1 text-[9px] font-semibold tracking-[0.08em] text-neutral-400 uppercase">
          {content.label}
        </p>
        <ul className="m-0 flex min-w-0 list-none gap-1.5 overflow-hidden p-0">
          {suggestions.map((suggestion, index) => (
            <li
              className={`shrink-0 rounded-full border border-black/5 bg-black/[0.035] px-2.5 py-1.5 transition-[opacity,transform] duration-200 ease-[cubic-bezier(0.23,1,0.32,1)] motion-reduce:translate-y-0 motion-reduce:transition-opacity ${index >= 2 ? 'hidden sm:block' : ''} ${
                entered ? 'translate-y-0 opacity-100' : 'translate-y-1 opacity-0'
              }`}
              key={`${suggestion.type}:${suggestion.name}`}
              style={{ transitionDelay: entered ? `${index * 40}ms` : '0ms' }}
            >
              <span className="text-[11px] font-medium whitespace-nowrap text-neutral-700">
                {suggestion.name}
              </span>
              <span className="ml-1.5 hidden text-[9px] whitespace-nowrap text-neutral-400 sm:inline">
                {suggestion.type}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  )
}
