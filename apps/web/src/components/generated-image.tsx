import type { GeneratedImage as GeneratedImageValue } from '@/stores/session'

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
 */

interface GeneratedImageProps {
  value: GeneratedImageValue
}

export function GeneratedImage({ value }: GeneratedImageProps) {
  return (
    <figure className="discovery-item generated-figure">
      {/* The prompt is the alt text, because the prompt is literally what is depicted. */}
      <img alt={value.prompt} className="generated-image" src={value.imageUrl} />
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
      </figcaption>
    </figure>
  )
}
