import type { Candidate } from '@glia/api-client'
import { useEffect, useMemo, useState } from 'react'
import { useSessionStore } from '@/stores/session'

export interface EntitySuggestion {
  name: string
  type: string
}

const MAX_SUGGESTIONS = 3

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

interface CalaEntityRailProps {
  previewSuggestions?: readonly EntitySuggestion[] | undefined
}

export function CalaEntityRail({ previewSuggestions }: CalaEntityRailProps) {
  const candidates = useSessionStore((state) => state.candidates)
  const generated = useSessionStore((state) => state.generation)
  const liveSuggestions = useMemo(() => suggestionsFrom(candidates), [candidates])
  const suggestions = previewSuggestions?.slice(0, MAX_SUGGESTIONS) ?? liveSuggestions
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

  if (generated || suggestions.length === 0) {
    return null
  }

  return (
    <aside
      aria-label="Cala related references"
      aria-live="polite"
      className={`pointer-events-none fixed right-3 bottom-[calc(var(--rail-space)+146px)] left-3 z-40 flex justify-center transition-[opacity,transform] duration-200 ease-[cubic-bezier(0.23,1,0.32,1)] motion-reduce:translate-y-0 motion-reduce:transition-opacity md:right-[330px] md:bottom-[calc(var(--rail-space)+96px)] md:left-[30vw] ${
        entered ? 'translate-y-0 opacity-100' : 'translate-y-2 opacity-0'
      }`}
    >
      <div className="flex min-w-0 max-w-full items-center gap-2 rounded-full border border-black/7 bg-white/88 px-2.5 py-2 shadow-[0_8px_28px_rgb(17_17_17/0.08)] backdrop-blur-md">
        <p className="m-0 shrink-0 pl-1 text-[9px] font-semibold tracking-[0.08em] text-neutral-400 uppercase">
          {previewSuggestions ? 'Demo · related' : 'Cala · related'}
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
