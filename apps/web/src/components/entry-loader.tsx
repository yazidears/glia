import { useEffect, useState } from 'react'

type LoaderStage = 'transcribing' | 'settling'

interface EntryLoaderProps {
  onComplete: () => void
}

const SETTLE_AT = 900
const COMPLETE_AT = 1_220

/** A brief first-visit cue: the phrase arrives as text, then becomes a visual signal. */
export function EntryLoader({ onComplete }: EntryLoaderProps) {
  const [stage, setStage] = useState<LoaderStage>('transcribing')

  useEffect(() => {
    const settleTimer = window.setTimeout(() => setStage('settling'), SETTLE_AT)
    const completeTimer = window.setTimeout(onComplete, COMPLETE_AT)

    return () => {
      window.clearTimeout(settleTimer)
      window.clearTimeout(completeTimer)
    }
  }, [onComplete])

  return (
    <div className="entry-loader" data-stage={stage} role="status" aria-live="polite">
      <p className="entry-loader-transcript">
        <span>Speak</span> <span>your</span> <span>mind.</span>
      </p>
    </div>
  )
}
