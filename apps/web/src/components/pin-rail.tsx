import { X } from 'lucide-react'
import { useGenerate } from '@/hooks/use-generate'
import { type PinnedRef, useSessionStore } from '@/stores/session'

/**
 * The conditioning input, made visible.
 *
 * The label says `conditioning input` rather than "Pinned" because that is the causal claim the
 * UI is making, and it is one the backend keeps: every pin's title goes into the prompt
 * synthesis, and every pin carrying a public image URL additionally goes to fal as a reference
 * image. A sticker has no public URL, so it steers the words and not the pixels — the result
 * view reports how many references actually landed, so the rail never has to overstate it.
 *
 * Absent at zero pins. There is nothing to condition on and nothing to say.
 *
 * It sits at the very bottom of the viewport, below the microphone, as a banner on its own
 * ground — the pins and the button that consumes them are one thing, and a shared surface is
 * what says so.
 */

const BUTTON_LABEL: Record<'idle' | 'generating', string> = {
  idle: 'Generate',
  generating: 'Generating',
}

function Thumbnail({ pin }: { pin: PinnedRef }) {
  if (pin.imageUrl) {
    return <img alt="" src={pin.imageUrl} className="pin-thumb-image" />
  }
  // No public URL, so there is no thumbnail to show and none is invented. The title is what
  // actually reaches the prompt, so the title is what the tile shows. It clamps at three lines;
  // the `title` attribute on the tile carries the rest.
  return <span className="pin-thumb-title">{pin.title}</span>
}

export function PinRail() {
  const pinned = useSessionStore((state) => state.pinned)
  const togglePin = useSessionStore((state) => state.togglePin)
  const generationError = useSessionStore((state) => state.generationError)
  const { generate, status, canGenerate } = useGenerate()

  if (pinned.length === 0) {
    return null
  }

  const generating = status === 'generating'

  return (
    <section aria-label="Conditioning input" className="pin-rail">
      <div className="pin-rail-inner">
        <div className="pin-rail-pins">
          <p className="pin-rail-label">
            {pinned.length} {pinned.length === 1 ? 'pin' : 'pins'} · conditioning input
          </p>
          <ul className="pin-thumbs">
            {pinned.map((pin) => (
              <li className="pin-thumb" key={pin.id} title={pin.title}>
                <span className="pin-thumb-media">
                  <Thumbnail pin={pin} />
                </span>
                {/*
                  Always visible, not revealed on hover. Unpinning is the one thing this rail is
                  for besides Generate, and an affordance you have to go looking for is not one.
                */}
                <button
                  type="button"
                  className="pin-thumb-remove"
                  aria-label={`Unpin ${pin.title}`}
                  onClick={() => togglePin(pin)}
                >
                  <X aria-hidden="true" strokeWidth={2.6} />
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="pin-rail-action">
          {/*
            The error stays beside the button rather than taking the workpane: it is one line,
            and the thing the user wants next is the same button, still clickable.
          */}
          {generationError ? (
            <p className="pin-rail-error" role="status">
              {generationError.message} Reference {generationError.correlationId}.
            </p>
          ) : null}
          <button
            type="button"
            className="pin-generate"
            data-generating={generating}
            disabled={!canGenerate}
            onClick={generate}
          >
            {BUTTON_LABEL[generating ? 'generating' : 'idle']}
          </button>
        </div>
      </div>
    </section>
  )
}
