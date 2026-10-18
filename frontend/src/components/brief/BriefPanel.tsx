/**
 * 動画の概要(主題・登場人物・固有名詞)の入力欄。
 *
 * すべてのAI処理(指示語の解決・切り抜き候補・固有名詞の質問など)のプロンプトに
 * 入り、精度に効く。以前は書き出しタブの中にあって見つけにくかったので、
 * 最初に開く文字起こしタブの先頭に、1行の帯として置く(未入力なら「未入力」と
 * 目立たせる)。押すと入力欄が開く。最初から開いておくと文字起こしの行と
 * AIへの指示欄の場所を奪い、開閉で行の位置がずれて操作を取り違えるので、
 * 開くのは利用者が押したときだけにする。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type Brief } from '../../api/client'

const FIELDS = [
  { key: 'theme', label: '動画全体の主題', placeholder: '例: AIと人の関わりについての対談' },
  {
    key: 'people',
    label: '登場人物の紹介',
    placeholder: '例: はやまる(古着店「箱ストア」店主)、高田さん(エッセイスト)',
  },
  {
    key: 'notes',
    label: '固有名詞・補足',
    placeholder: '例: 「箱ストア」は店名。「富山変人会」は二人が出会ったイベント',
  },
] as const

type BriefKey = (typeof FIELDS)[number]['key']

export function BriefPanel({ mediaId }: { mediaId: number }) {
  const queryClient = useQueryClient()
  const brief = useQuery({ queryKey: ['brief', mediaId], queryFn: () => api.getBrief(mediaId) })
  const save = useMutation({
    mutationFn: (patch: Partial<Brief>) => api.updateBrief(mediaId, { ...brief.data, ...patch }),
    onSuccess: (data) => queryClient.setQueryData(['brief', mediaId], data),
  })
  const [expanded, setExpanded] = useState(false)

  if (!brief.data) return null
  const value = (key: BriefKey) => brief.data[key] ?? ''
  const empty = FIELDS.every((f) => !value(f.key).trim())

  return (
    <section
      data-testid="brief-panel"
      className="border-b border-neutral-200 bg-amber-50/60 dark:border-neutral-800 dark:bg-amber-950/30"
    >
      <button
        type="button"
        data-testid="brief-toggle"
        aria-expanded={expanded}
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-baseline gap-2 px-3 py-2 text-left text-xs"
      >
        <span aria-hidden="true">{expanded ? '▼' : '▶'}</span>
        <span className="font-semibold text-neutral-700 dark:text-neutral-200">動画の概要</span>
        {empty && (
          <span className="rounded bg-amber-200 px-1.5 text-[10px] font-semibold text-amber-900 dark:bg-amber-800 dark:text-amber-100">
            未入力
          </span>
        )}
        <span className="min-w-0 flex-1 truncate text-neutral-500">
          {empty
            ? '入力するとAIの精度が上がります(主題・登場人物・固有名詞)'
            : value('theme') || value('people') || value('notes')}
        </span>
      </button>
      {expanded && (
        <div className="max-h-[45vh] space-y-2 overflow-y-auto px-3 pb-3">
          <p className="text-xs text-neutral-500">
            指示語の解決・切り抜き候補・固有名詞の確認など、すべてのAI処理で参考にします。
          </p>
          {FIELDS.map((f) => (
            <label key={f.key} className="block text-xs">
              <span className="text-neutral-500">{f.label}</span>
              <textarea
                data-testid={`brief-${f.key}`}
                className="mt-0.5 w-full rounded border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900"
                rows={2}
                defaultValue={value(f.key)}
                placeholder={f.placeholder}
                onBlur={(e) => {
                  if (e.target.value !== value(f.key)) save.mutate({ [f.key]: e.target.value })
                }}
              />
            </label>
          ))}
          {save.isSuccess && <p className="text-xs text-emerald-600">保存しました</p>}
        </div>
      )}
    </section>
  )
}
