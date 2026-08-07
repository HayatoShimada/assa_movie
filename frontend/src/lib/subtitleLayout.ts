/**
 * 字幕オーバーレイの位置・サイズ(プレビュー用)。
 *
 * backendの `scaled_style`(backend/pipeline/subtitle.py)と同じ規則を
 * コンテナクエリ単位で表す純関数:
 *   - フォント・左右余白は「出力幅に対する比率」(基準 1920px)
 *   - 上下余白は「出力高さに対する比率」(基準 1080px)
 * これにより、どの出力向き・ウィンドウ幅でも書き出しと同じ見た目比率になる。
 * 期待値は tests/test_m13_subtitle_style.py と対応(subtitleLayout.test.ts参照)。
 */
export const BASE_RES_X = 1920
export const BASE_RES_Y = 1080
const BASE_MARGIN_V = 40 // 上下の既定余白(1080px基準)
const BASE_MARGIN_H = 60 // 左右の余白(1920px基準)
const OFFSET_LIMIT = 120 // 上下微調整の上限(backendと同じ)

export type SubtitlePosition = 'top' | 'center' | 'bottom'

export interface OverlayGeometry {
  /** 縦位置。centerのみtop+transformで中央寄せする */
  top?: string
  bottom?: string
  transform?: string
  left: string
  right: string
  fontSize: string
}

const cqw = (px: number) => `${((px / BASE_RES_X) * 100).toFixed(3)}cqw`
const cqh = (px: number) => `${((Math.max(0, px) / BASE_RES_Y) * 100).toFixed(3)}cqh`

export function overlayGeometry(
  position: SubtitlePosition,
  offsetY: number,
  fontSize: number,
): OverlayGeometry {
  // offsetY: +で下へ、-で上へ(backendのscaled_styleと同じ向き)
  const offset = Math.max(-OFFSET_LIMIT, Math.min(OFFSET_LIMIT, offsetY))
  const common = { left: cqw(BASE_MARGIN_H), right: cqw(BASE_MARGIN_H), fontSize: cqw(fontSize) }
  if (position === 'top') return { ...common, top: cqh(BASE_MARGIN_V + offset) }
  if (position === 'center') return { ...common, top: '50%', transform: 'translateY(-50%)' }
  return { ...common, bottom: cqh(BASE_MARGIN_V - offset) }
}

/** #RRGGBB + 不透明度 → CSS rgba(背景ボックス用) */
export function hexToRgba(hex: string, opacity: number): string {
  const h = hex.replace('#', '')
  if (!/^[0-9a-fA-F]{6}$/.test(h)) return `rgba(0,0,0,${opacity})`
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16))
  return `rgba(${r},${g},${b},${opacity})`
}
