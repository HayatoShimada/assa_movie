/**
 * 用語の横に置く「?」。マウスを乗せる・キーボードでフォーカスすると説明が出る。
 *
 * button にしないのは、設定の行(<label>)の中に置いたとき、行のクリックが
 * select ではなくこちらに吸われるため(label は最初のラベル可能な要素を操作する)。
 * 説明は開いている間だけ描く。隠したまま置いておくと、説明文の中の語
 * (「反動体」等)が画面の本文と同じ文字列として二重に見つかってしまう。
 */
import { useState } from 'react'
import { GLOSSARY, type GlossaryTerm } from '../lib/glossary'

export function HelpTip({
  term,
  text,
  align = 'center',
}: {
  term?: GlossaryTerm
  text?: string
  /** 画面の右端に置くときは right(説明が画面外にはみ出さないように) */
  align?: 'center' | 'right'
}) {
  const body = text ?? (term ? GLOSSARY[term] : '')
  const [open, setOpen] = useState(false)
  return (
    <span
      className="relative ml-1 inline-flex align-middle"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      // 行(<label>)の中で押しても、チェックボックス等が切り替わらないようにする
      onClick={(e) => e.preventDefault()}
    >
      <span
        tabIndex={0}
        role="img"
        aria-label={`${term ?? '用語'}の説明`}
        data-testid={term ? `help-${term}` : undefined}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-neutral-400 text-[10px] leading-none text-neutral-500 focus-visible:outline-2 focus-visible:outline-blue-500 dark:border-neutral-500"
      >
        ?
      </span>
      {open && (
        <span
          role="tooltip"
          className={`pointer-events-none absolute top-5 z-30 w-64 ${
            align === 'right' ? 'right-0' : 'left-1/2 -translate-x-1/2'
          } rounded-md bg-neutral-900 px-2 py-1.5 text-xs font-normal leading-relaxed text-white shadow-lg dark:bg-neutral-100 dark:text-neutral-900`}
        >
          {body}
        </span>
      )}
    </span>
  )
}
