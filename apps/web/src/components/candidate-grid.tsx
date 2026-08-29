import { CandidateTile } from '@/components/candidate-tile'
import { cn } from '@/lib/utils'
import { useSessionStore } from '@/stores/session'

interface CandidateGridProps {
  className?: string
}

/**
 * The workpane's primary content: what the open corpora found for what you just said.
 *
 * Reads the store directly rather than taking a prop, because candidates arrive over the
 * WebSocket in waves and every wave must reach the screen without a parent re-render
 * deciding to hold one back.
 */
export function CandidateGrid({ className }: CandidateGridProps) {
  const candidates = useSessionStore((state) => state.candidates)
  const removeCandidate = useSessionStore((state) => state.removeCandidate)

  if (candidates.length === 0) {
    return null
  }

  return (
    <section aria-label="Discovered images" className={cn('candidate-grid', className)}>
      {candidates.map((candidate, index) => (
        <CandidateTile
          key={candidate.id}
          candidate={candidate}
          index={index}
          onUnavailable={removeCandidate}
        />
      ))}
    </section>
  )
}
