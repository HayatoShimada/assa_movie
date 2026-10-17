/** 小さな共通UI部品。本格的なデザインは全機能完成後に調整する(CLAUDE.md)。 */
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from 'react'
import type { StateTone } from '../lib/media'

export function Button({
  variant = 'primary',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'ghost' | 'danger' }) {
  const styles = {
    primary: 'bg-blue-600 text-white hover:bg-blue-700 disabled:bg-neutral-300',
    ghost:
      'border border-neutral-300 hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800',
    danger: 'bg-red-600 text-white hover:bg-red-700 disabled:opacity-50',
  }[variant]
  return (
    <button
      // キーボード操作で今どこにいるかが見えるよう、フォーカス枠は必ず出す
      className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 disabled:cursor-not-allowed ${styles} ${className}`}
      {...props}
    />
  )
}

export function ProgressBar({
  value,
  label,
  'data-testid': testId,
}: {
  value: number
  label?: string
  'data-testid'?: string
}) {
  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(value * 100)}
      data-testid={testId}
      className="w-full"
    >
      {label && <p className="mb-1 text-xs text-neutral-500">{label}</p>}
      <div className="h-2 overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-800">
        <div
          className="h-full rounded-full bg-blue-600 transition-[width] duration-300"
          style={{ width: `${Math.round(value * 100)}%` }}
        />
      </div>
    </div>
  )
}

const SPEAKER_COLORS = [
  'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  'bg-rose-100 text-rose-800 dark:bg-rose-900 dark:text-rose-200',
  'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200',
  'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200',
]

/** 話者名から安定した色を割り当てる */
export function speakerColor(name: string): string {
  let hash = 0
  for (const ch of name) hash = (hash * 31 + ch.codePointAt(0)!) >>> 0
  return SPEAKER_COLORS[hash % SPEAKER_COLORS.length]
}

export function SpeakerBadge({ name }: { name: string }) {
  return (
    <span
      className={`inline-block shrink-0 rounded px-1.5 py-0.5 text-xs font-medium ${speakerColor(name)}`}
    >
      {name}
    </span>
  )
}

export function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-neutral-200 p-4 dark:border-neutral-800">
      <h2 className="mb-2 font-semibold">{title}</h2>
      {children}
    </section>
  )
}

const TONE_STYLES: Record<StateTone, string> = {
  neutral: 'bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300',
  busy: 'bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300',
  done: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300',
  error: 'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300',
}

const DOT_STYLES: Record<StateTone, string> = {
  neutral: 'bg-neutral-400',
  busy: 'bg-blue-500 motion-safe:animate-pulse',
  done: 'bg-emerald-500',
  error: 'bg-red-500',
}

/** 状態を色と言葉の両方で示す小さな札(色だけに頼らない) */
export function StateBadge({
  tone,
  children,
  className = '',
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone: StateTone }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${TONE_STYLES[tone]} ${className}`}
      {...props}
    >
      <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${DOT_STYLES[tone]}`} />
      {children}
    </span>
  )
}

/** フォーム部品(select/input)の共通クラス。
 * 文字色と背景は明示する。継承任せにするとネイティブ描画のselect
 * (色はCSS・箱はOSテーマ)で白文字がライトな箱に沈むことがある(Ubuntu版で実例) */
export const selectCls =
  'rounded-md border border-neutral-300 bg-white px-2 py-1 text-sm text-neutral-900 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100'

/** 秒を 1:23 / 1:02:03 形式にする */
export function formatTime(seconds: number): string {
  const s = Math.floor(seconds)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = String(s % 60).padStart(2, '0')
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`
}
