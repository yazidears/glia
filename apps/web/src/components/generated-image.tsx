import { useState } from 'react'
import { SessionReport } from '@/components/session-report'
import type { GeneratedImage as GeneratedImageValue } from '@/stores/session'
import { useSessionStore } from '@/stores/session'

/**
 * The result of Generate.
 *
 * The prompt underneath is not a caption and not a summary — it is the exact string the server
 * sent to fal, printed verbatim. That is the product's claim made checkable: *here is what we
 * understood you to mean*, and here is the thing it produced.
 *
 * `references` says how many pins fal actually received as image conditioning. Zero is the
 * normal case for a board of stickers, which have no URL at all — and it is stated rather than
 * hidden, because the alternative is implying a conditioning that did not happen.
 *
 * A pin the server could not fetch or re-host is dropped rather than fatal, so the image above
 * is real and simply had less to go on. Saying so is the whole point: the user is the only one
 * who can act on it, and they cannot act on a number that quietly came back one short.
 *
 * The report opens from here rather than from the rail because this is the moment it means
 * something: an image exists, so there is a session to write up. Before that there is no report,
 * and an affordance for a document that cannot exist yet is noise.
 */

interface GeneratedImageProps {
  value: GeneratedImageValue
}

export function GeneratedImage({ value }: GeneratedImageProps) {
  const [failedImageUrl, setFailedImageUrl] = useState<string | null>(null)
  const markGenerationImageReady = useSessionStore((state) => state.markGenerationImageReady)
  const previewFailed = failedImageUrl === value.imageUrl

  const finishPreview = (): void => {
    markGenerationImageReady()
  }

  const failPreview = (): void => {
    setFailedImageUrl(value.imageUrl)
    // Do not strand the convergence layer over a result whose CDN preview failed. The honest
    // inline error underneath replaces it and leaves the exact fal URL available to retry.
    markGenerationImageReady()
  }

  return (
    <figure className="discovery-item generated-figure">
      {previewFailed ? (
        <div className="generated-preview-error" role="status">
          <p>The image was generated, but its preview could not be loaded.</p>
          <a href={value.imageUrl} rel="noreferrer" target="_blank">
            Open the fal result
          </a>
        </div>
      ) : (
        /* The prompt is the alt text, because the prompt is literally what is depicted. */
        <img
          alt={value.prompt}
          className="generated-image"
          decoding="async"
          onError={failPreview}
          onLoad={finishPreview}
          src={value.imageUrl}
        />
      )}
      <figcaption className="generated-caption">
        <p className="generated-prompt">{value.prompt}</p>
        <p className="generated-meta">
          <span>{value.model}</span>
          <span aria-hidden="true">·</span>
          <span>
            {value.referenceCount}{' '}
            {value.referenceCount === 1 ? 'reference image' : 'reference images'}
          </span>
        </p>
        {value.unavailableReferences.length > 0 && (
          <p className="generated-dropped">
            {value.unavailableReferences.length === 1
              ? '1 pin'
              : `${value.unavailableReferences.length} pins`}{' '}
            could not be fetched and did not condition this image.
          </p>
        )}
        <SessionReport generated={value} />
      </figcaption>
    </figure>
  )
}
