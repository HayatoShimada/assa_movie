import { describe, expect, it } from 'vitest'
import { parseHash, toHash, type Route } from './useHashRoute'

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

  it('#/settings は全体の設定', () => {
    expect(parseHash('#/settings')).toEqual({ page: 'settings' })
    expect(parseHash('#/settings/')).toEqual({ page: 'settings' })
    expect(parseHash('#/settingsx')).toEqual({ page: 'home' })
  })

  it('toHash と parseHash は往復で一致する', () => {
    const routes: Route[] = [{ page: 'home' }, { page: 'editor', mediaId: 7 }, { page: 'settings' }]
    for (const r of routes) expect(parseHash(toHash(r))).toEqual(r)
  })
})
