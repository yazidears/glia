import type { GeneratedImage as GeneratedImageValue } from '@/stores/session'

/**
 * The result of Generate.
 *
 * The prompt underneath is not a caption and not a summary — it is the exact string the server
 * sent to fal, printed verbatim. That is the product's claim made checkable: *here is what we
 * understood you to mean*, and here is the thing it produced.
 *
 * `references` says how many pins fal actually received as image conditioning. Zero is the
 * normal case today, because the board's stickers have no public URL — and it is stated rather
 * than hidden, because the alternative is implying a conditioning that did not happen.
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
      </figcaption>
    </figure>
  )
}
