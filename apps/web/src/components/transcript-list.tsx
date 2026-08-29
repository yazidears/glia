/**
 * Transcript lines, oldest first, growing upward above the docked microphone.
 *
 * Nothing is transcribed yet, so this renders nothing at all — no placeholder copy, no skeleton.
 * The list exists now so the scroll container around it is already the right shape when lines
 * start arriving.
 */
export function TranscriptList() {
  return <ol className="flex flex-col gap-2 text-sm" />
}
