import { describe, expect, it } from 'vitest'
import { parseHash } from './useHashRoute'

describe('parseHash', () => {
  it('空ハッシュはホーム', () => {
    expect(parseHash('')).toEqual({ page: 'home' })
    expect(parseHash('#/')).toEqual({ page: 'home' })
  })

  it('#/media/3 はエディタ', () => {
    expect(parseHash('#/media/3')).toEqual({ page: 'editor', mediaId: 3 })
  })

  it('不正なパスはホームに落とす', () => {
    expect(parseHash('#/media/abc')).toEqual({ page: 'home' })
    expect(parseHash('#/nope')).toEqual({ page: 'home' })
  })
})
