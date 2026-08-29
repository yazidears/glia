import { useEffect, useRef } from 'react'
import { useGenerate } from '@/hooks/use-generate'
import { demoRevealCount, visibleCandidateRefs, visibleDemoRefs } from '@/lib/pinned-references'
import { voiceCommandFor } from '@/lib/voice-commands'
import { useSessionStore } from '@/stores/session'

/** Executes completed control utterances once, while leaving them visible in the transcript. */
export function useVoiceCommands(): void {
  const segments = useSessionStore((state) => state.transcriptSegments)
  const candidates = useSessionStore((state) => state.candidates)
  const intentSource = useSessionStore((state) => state.intentUpdate?.source)
  const pinned = useSessionStore((state) => state.pinned)
  const pinMany = useSessionStore((state) => state.pinMany)
  const handledItems = useRef(new Set<string>())
  const { generate } = useGenerate()

  useEffect(() => {
    for (const segment of segments) {
      if (!segment.complete || handledItems.current.has(segment.itemId)) {
        continue
      }
      const command = voiceCommandFor(segment.text)
      if (!command) {
        continue
      }
      handledItems.current.add(segment.itemId)

      if (command === 'generate') {
        generate()
        continue
      }

      const ideaWordCount = segments
        .filter((item) => voiceCommandFor(item.text) === null)
        .flatMap((item) => item.text.trim().split(/\s+/))
        .filter(Boolean).length
      const visible =
        candidates.length > 0
          ? visibleCandidateRefs(candidates, pinned)
          : intentSource === 'fixture'
            ? visibleDemoRefs(pinned, demoRevealCount(ideaWordCount))
            : []
      pinMany(visible)
    }
  }, [candidates, generate, intentSource, pinMany, pinned, segments])
}
