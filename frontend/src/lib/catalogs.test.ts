import { describe, expect, it } from 'vitest'
import { TEMPLATES, templateDescription } from './catalogs'

const byId = (id: string) => TEMPLATES.find((t) => t.id === id)!

describe('templateDescription(作成時に、選んだテンプレートで何が起きるかを1行で出す)', () => {
  it('向きが同じなら、そのままの向きで書き出す', () => {
    expect(templateDescription(byId('l2l'), 'blur_pad')).toBe(
      '横長の動画を、そのまま横長(1920×1080)で書き出します。',
    )
    expect(templateDescription(byId('p2p'), 'crop')).toBe(
      '縦長の動画を、そのまま縦長(1080×1920)で書き出します。',
    )
  })

  it('向きを変えるときは、収まらない部分の扱い(今の変換方式)を書く', () => {
    expect(templateDescription(byId('l2p'), 'blur_pad')).toBe(
      '横長の動画から縦長(1080×1920)の切り抜きを作ります。映像は切らずに全体を表示し、上下の余白をぼかした映像で埋めます。',
    )
    expect(templateDescription(byId('l2p'), 'crop')).toBe(
      '横長の動画から縦長(1080×1920)の切り抜きを作ります。左右を切り落とします(残す位置はクリップごとに調整できます)。',
    )
    expect(templateDescription(byId('p2l'), 'crop')).toBe(
      '縦長の動画から横長(1920×1080)の切り抜きを作ります。上下を切り落とします(残す位置はクリップごとに調整できます)。',
    )
    expect(templateDescription(byId('l2p'), 'face')).toBe(
      '横長の動画から縦長(1080×1920)の切り抜きを作ります。顔を検出し、1人なら顔に合わせて切り出し、2人なら上下に並べます(見つからなければぼかし背景)。',
    )
  })

  it('縦→横のぼかしは左右の余白を埋める', () => {
    expect(templateDescription(byId('p2l'), 'blur_pad')).toContain('左右の余白')
  })
})
