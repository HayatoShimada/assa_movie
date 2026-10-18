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

const ORIENTATION_NAME: Record<Orientation, string> = {
  landscape: '横長(1920×1080)',
  portrait: '縦長(1080×1920)',
}

/**
 * 選んだテンプレートで何が起きるかの1行説明(作成フォームに出す)。
 *
 * 向きを変えるときの「収まらない部分の扱い」は変換方式(convert_method)で決まるので、
 * いま効いている方式を受け取って書く。書き出し側の実装は backend/pipeline/layout.py
 */
export function templateDescription(t: Template, method: ConvertMethod): string {
  const from = t.input === 'landscape' ? '横長' : '縦長'
  if (t.input === t.output) {
    return `${from}の動画を、そのまま${ORIENTATION_NAME[t.output]}で書き出します。`
  }
  const head = `${from}の動画から${ORIENTATION_NAME[t.output]}の切り抜きを作ります。`
  // 横→縦は左右がはみ出し上下が余る。縦→横はその逆
  const cut = t.output === 'portrait' ? '左右' : '上下'
  const pad = t.output === 'portrait' ? '上下' : '左右'
  const how: Record<ConvertMethod, string> = {
    crop: `${cut}を切り落とします(残す位置はクリップごとに調整できます)。`,
    blur_pad: `映像は切らずに全体を表示し、${pad}の余白をぼかした映像で埋めます。`,
    face: '顔を検出し、1人なら顔に合わせて切り出し、2人なら上下に並べます(見つからなければぼかし背景)。',
  }
  return head + (how[method] ?? '')
}

export function templateFor(project: Pick<Project, 'input_orientation' | 'output_orientation'>) {
  return TEMPLATES.find(
    (t) => t.input === project.input_orientation && t.output === project.output_orientation,
  )
}
