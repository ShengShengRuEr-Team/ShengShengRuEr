import { describe, expect, it } from 'vitest'

describe('test toolchain smoke', () => {
  it('has jsdom globals and jest-dom matchers', () => {
    const element = document.createElement('div')
    element.textContent = 'ready'
    document.body.appendChild(element)
    expect(element).toBeInTheDocument()
    expect(window.localStorage).toBeDefined()
  })
})
