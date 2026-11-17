import { describe, expect, it } from 'vitest'
import { routerBasename } from './basename'

describe('routerBasename', () => {
  it('根路径保持 /，子路径去掉尾斜杠', () => {
    expect(routerBasename('/')).toBe('/')
    expect(routerBasename('/listening/')).toBe('/listening')
    expect(routerBasename('/listening')).toBe('/listening')
  })
})
