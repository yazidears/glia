import { cn } from '@/lib/utils'

interface WorkpaneProps {
  className?: string
}

/**
 * The right two thirds of the working layout: where discovered images and the generated result
 * will land. Deliberately an empty region — placeholder art would only have to be removed.
 */
export function Workpane({ className }: WorkpaneProps) {
  return <section aria-label="Workpane" className={cn('min-h-0 p-5 md:p-8', className)} />
}
