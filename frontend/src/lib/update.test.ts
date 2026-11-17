import { describe, expect, it } from 'vitest'
import { dismiss, isDismissed } from './update'

function memoryStore() {
  const data = new Map<string, string>()
  return {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
  }
}

describe('新しい版のお知らせを閉じた記録', () => {
  it('閉じた版は出さない', () => {
    const store = memoryStore()
    expect(isDismissed('2.1.0', store)).toBe(false)
    dismiss('2.1.0', store)
    expect(isDismissed('2.1.0', store)).toBe(true)
  })

  it('さらに新しい版が出たらまた知らせる', () => {
    const store = memoryStore()
    dismiss('2.1.0', store)
    expect(isDismissed('2.2.0', store)).toBe(false)
  })

  it('最新版が分からなければ「閉じた」扱いにしない', () => {
    expect(isDismissed(null, memoryStore())).toBe(false)
  })

  it('保存領域が使えなくても落ちない(毎回出すだけ)', () => {
    const broken = {
      getItem: () => {
        throw new Error('denied')
      },
      setItem: () => {
        throw new Error('denied')
      },
    }
    expect(isDismissed('2.1.0', broken)).toBe(false)
    expect(() => dismiss('2.1.0', broken)).not.toThrow()
  })
})
