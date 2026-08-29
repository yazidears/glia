import { Component, type ErrorInfo, type ReactNode } from 'react'

interface PanelBoundaryProps {
  children: ReactNode
  /** Rendered in place of the children when the subtree throws. */
  fallback: ReactNode
}

interface PanelBoundaryState {
  failed: boolean
}

/**
 * Keeps one panel's failure inside that panel.
 *
 * The workpane shows two independent things and only one of them is the product. A throw
 * while rendering the Cala answer — a markdown shape the parser chokes on, an origin the
 * evidence card did not expect — used to take the whole pane with it, including a grid of
 * images that had already arrived and were entirely fine. This is the wall between them.
 */
export class PanelBoundary extends Component<PanelBoundaryProps, PanelBoundaryState> {
  override state: PanelBoundaryState = { failed: false }

  static getDerivedStateFromError(): PanelBoundaryState {
    return { failed: true }
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // Kept out of the UI on purpose: the panel says something short and human, and the
    // stack goes where a developer will look for it.
    console.error('Workpane panel failed to render.', error, info.componentStack)
  }

  override render(): ReactNode {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}
