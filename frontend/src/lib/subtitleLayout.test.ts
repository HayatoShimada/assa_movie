import { describe, expect, it } from 'vitest'
import { hexToRgba, overlayGeometry } from './subtitleLayout'

describe('overlayGeometry(backendのscaled_styleと同じ規則)', () => {
  it('フォントは出力幅に対する比率(48px@1920 = 2.5%)', () => {
    expect(overlayGeometry('bottom', 0, 48).fontSize).toBe('2.500cqw')
    expect(overlayGeometry('bottom', 0, 96).fontSize).toBe('5.000cqw')
  })

  it('左右余白は60px@1920基準で固定', () => {
    const g = overlayGeometry('bottom', 0, 48)
    expect(g.left).toBe('3.125cqw')
    expect(g.right).toBe('3.125cqw')
  })

  it.each([
    ['bottom', 0, { bottom: '3.704cqh' }],   // 40/1080
    ['bottom', 30, { bottom: '0.926cqh' }],  // +は下 → 余白が減る (40-30)/1080
    ['top', 0, { top: '3.704cqh' }],
    ['top', 20, { top: '5.556cqh' }],        // +は下 → 上余白は増える (40+20)/1080
  ] as const)('位置 %s / オフセット %s', (position, offset, expected) => {
    expect(overlayGeometry(position, offset, 48)).toMatchObject(expected)
  })

  it('中央でもオフセット分ずれる(書き出しの \\pos と同じ量)', () => {
    expect(overlayGeometry('center', 0, 48)).toMatchObject({
      top: '50%',
      transform: 'translateY(calc(-50% + 0.000cqh))',
    })
    // +54px@1080 = 高さの5%下へ
    expect(overlayGeometry('center', 54, 48).transform).toBe(
      'translateY(calc(-50% + 5.000cqh))',
    )
    expect(overlayGeometry('center', -54, 48).transform).toBe(
      'translateY(calc(-50% + -5.000cqh))',
    )
    expect(overlayGeometry('center', 100, 48).bottom).toBeUndefined()
  })

  it('オフセットは±120でクランプし、余白は0未満にならない', () => {
    expect(overlayGeometry('bottom', 999, 48).bottom).toBe('0.000cqh')
    expect(overlayGeometry('top', -999, 48).top).toBe('0.000cqh')
  })
})

describe('hexToRgba', () => {
  it.each([
    ['#000000', 0.5, 'rgba(0,0,0,0.5)'],
    ['#FFFFFF', 1, 'rgba(255,255,255,1)'],
    ['#FF8000', 0.25, 'rgba(255,128,0,0.25)'],
    ['ff0000', 1, 'rgba(255,0,0,1)'],
  ])('%s → %s', (hex, opacity, expected) => {
    expect(hexToRgba(hex, opacity)).toBe(expected)
  })

  it('不正な色は黒にフォールバックする(描画を止めない)', () => {
    expect(hexToRgba('赤', 0.5)).toBe('rgba(0,0,0,0.5)')
  })
})
