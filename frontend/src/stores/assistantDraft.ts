let queuedImage: File | null = null

/** Keep a selected homepage image while the SPA navigates to the authenticated AI workflow. */
export function queueAssistantImage(file: File): void {
  queuedImage = file
}

export function takeAssistantImage(): File | null {
  const file = queuedImage
  queuedImage = null
  return file
}
