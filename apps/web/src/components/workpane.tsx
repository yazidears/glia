import { GeneratedImage } from '@/components/generated-image'
import { IdeaBoard } from '@/components/idea-board'
import { cn } from '@/lib/utils'
import { useSessionStore } from '@/stores/session'

interface WorkpaneProps {
  className?: string
}

/**
 * The visual half of the live workspace.
 *
 * Candidate discovery belongs to the realtime socket: it can stream open references while the
 * speaker is still talking and then refine the same board after Fastino/OpenAI/Cala settle. This
 * component must not start a second REST discovery, which would add latency and spend Cala twice.
 */
export function Workpane({ className }: WorkpaneProps) {
  const generated = useSessionStore((state) => state.generation)

  if (generated) {
    return (
      <section
        aria-label="Generated image"
        className={cn('flex min-h-0 flex-col overflow-y-auto p-5 md:p-8', className)}
      >
        <GeneratedImage value={generated} />
      </section>
    )
  }

  return <IdeaBoard className={className} />
}
