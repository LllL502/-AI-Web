import { expect, it } from 'vitest'
import { queueAssistantImage, takeAssistantImage } from '../../src/stores/assistantDraft'

it('transfers a selected homepage image once into the assistant workflow', () => {
  const image = new File(['image bytes'], 'campus-card.png', { type: 'image/png' })
  queueAssistantImage(image)
  expect(takeAssistantImage()).toBe(image)
  expect(takeAssistantImage()).toBeNull()
})
