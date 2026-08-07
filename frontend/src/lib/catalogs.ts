/**
 * UIの選択肢カタログ(テンプレート・変換方式)。
 *
 * コンポーネントから分離しておくことで、作成フォームと設定パネルの双方が
 * 同じ定義を参照でき、文言の食い違いが起きない。
 */
import type { Orientation, Project } from '../api/client'

export type ConvertMethod = 'crop' | 'blur_pad' | 'face'

export const CONVERT_METHOD_LABELS: Record<ConvertMethod, string> = {
  crop: '中央クロップ(位置調整可)',
  blur_pad: 'ぼかし背景(全体表示)',
  face: '顔検出(1人=追従クロップ / 2人=上下分割)',
}

export interface Template {
  id: string
  label: string
  input: Orientation
  output: Orientation
}

/** 入力の向き × 出力の向き の4通り(backendのinput/output_orientationに対応) */
export const TEMPLATES: Template[] = [
  { id: 'l2l', label: '横 → 横', input: 'landscape', output: 'landscape' },
  { id: 'l2p', label: '横 → 縦', input: 'landscape', output: 'portrait' },
  { id: 'p2p', label: '縦 → 縦', input: 'portrait', output: 'portrait' },
  { id: 'p2l', label: '縦 → 横', input: 'portrait', output: 'landscape' },
]

export function templateFor(project: Pick<Project, 'input_orientation' | 'output_orientation'>) {
  return TEMPLATES.find(
    (t) => t.input === project.input_orientation && t.output === project.output_orientation,
  )
}
