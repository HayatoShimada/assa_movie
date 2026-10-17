/**
 * 名前・用語の辞書(設定タブ)。
 *
 * 質問タブで答えた固有名詞の正しい表記を、プロジェクトや動画をまたいで覚えておき、
 * 次の文字起こしでWhisperにヒントとして渡す(backend/core/user_terms.py)。
 * ここで見て・足して・直して・消せる。変更はその場で保存する(APIキーと同じ流儀)。
 *
 * Whisperに渡せる量には上限があるので、上から順(よく答えた語・最近の語)に使う。
 * 溢れた語は「今回は使いません」と示す(黙って効かないのがいちばん困るため)。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { ApiError, api, type UserTerm } from '../../api/client'
import { formatTermList, parseTermList } from '../../lib/userTerms'
import { Button, selectCls } from '../ui'

const QUERY_KEY = ['user-terms']

function errorText(error: unknown, fallback: string): string {
  // ApiError.detail は client.ts が {"detail": "..."} から取り出し済み(生のJSONではない)
  return error instanceof ApiError && error.detail ? error.detail : fallback
}

function TermRow({ item, enabled }: { item: UserTerm; enabled: boolean }) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [term, setTerm] = useState(item.term)
  const [wrongs, setWrongs] = useState(formatTermList(item.misrecognitions))
  const refresh = () => queryClient.invalidateQueries({ queryKey: QUERY_KEY })

  const save = useMutation({
    mutationFn: () =>
      api.updateUserTerm(item.id, { term: term.trim(), misrecognitions: parseTermList(wrongs) }),
    onSuccess: () => {
      setEditing(false)
      refresh()
    },
  })
  const remove = useMutation({ mutationFn: () => api.deleteUserTerm(item.id), onSuccess: refresh })

  return (
    <li
      data-testid={`user-term-row-${item.id}`}
      className="border-t border-neutral-200 py-2 first:border-t-0 dark:border-neutral-800"
    >
      {editing ? (
        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (term.trim()) save.mutate()
          }}
        >
          <input
            aria-label="正しい表記"
            className={`${selectCls} w-full`}
            value={term}
            onChange={(e) => setTerm(e.target.value)}
          />
          <input
            aria-label="以前の聞き間違い"
            className={`${selectCls} w-full`}
            placeholder="以前の聞き間違い(「、」で区切る。例: 反動体、はんどう体)"
            value={wrongs}
            onChange={(e) => setWrongs(e.target.value)}
          />
          <div className="flex gap-2">
            <Button type="submit" disabled={!term.trim() || save.isPending}>
              保存
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setEditing(false)
                setTerm(item.term)
                setWrongs(formatTermList(item.misrecognitions))
                save.reset()
              }}
            >
              やめる
            </Button>
          </div>
          {save.isError && (
            <p className="text-xs text-red-600">{errorText(save.error, '保存できませんでした')}</p>
          )}
        </form>
      ) : (
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-medium">
              {item.term}
              {enabled && !item.used_for_asr && (
                <span className="ml-2 text-xs font-normal text-amber-600">
                  上限のため今回は使いません
                </span>
              )}
            </p>
            {item.misrecognitions.length > 0 && (
              <p className="text-xs text-neutral-500">
                以前の聞き間違い: {formatTermList(item.misrecognitions)}
              </p>
            )}
          </div>
          <div className="flex shrink-0 gap-2">
            <Button type="button" variant="ghost" onClick={() => setEditing(true)}>
              直す
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => remove.mutate()}
              disabled={remove.isPending}
            >
              削除
            </Button>
          </div>
        </div>
      )}
    </li>
  )
}

export function UserTermsPanel() {
  const queryClient = useQueryClient()
  const terms = useQuery({ queryKey: QUERY_KEY, queryFn: api.listUserTerms })
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  const [draft, setDraft] = useState('')
  const add = useMutation({
    mutationFn: (term: string) => api.addUserTerm(term),
    onSuccess: () => {
      setDraft('')
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    },
  })
  // 設定の読み込み前は「使う」扱い(既定値)。使わない設定のときだけ案内を出す
  const enabled = settings.data?.values.asr_use_user_terms !== false
  const items = terms.data ?? []
  const overflow = enabled && items.some((t) => !t.used_for_asr)

  return (
    <section
      data-testid="user-terms-panel"
      className="mb-4 rounded-lg border border-neutral-200 p-3 dark:border-neutral-800"
    >
      <h3 className="mb-1 text-sm font-semibold">名前・用語の辞書</h3>
      <p className="mb-2 text-xs text-neutral-500">
        よく出る人の名前・会社名・専門用語を覚えて、次の文字起こしで正しく書けるようにします。
        質問タブで答えた表記は、ここに自動で追加されます。どのプロジェクトでも使われます。
      </p>
      {!enabled && (
        <p data-testid="user-terms-disabled" className="mb-2 text-xs text-amber-600">
          いまは辞書を使わない設定です。下の「文字起こし」にある「名前・用語の辞書を使う」で切り替えられます。
        </p>
      )}
      <form
        className="mb-2 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (draft.trim()) add.mutate(draft.trim())
        }}
      >
        <input
          data-testid="user-term-input"
          aria-label="辞書に追加する名前・用語"
          className={`${selectCls} flex-1`}
          placeholder="名前や用語を追加(例: 半導体)"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <Button data-testid="user-term-add" type="submit" disabled={!draft.trim() || add.isPending}>
          追加
        </Button>
      </form>
      {add.isError && (
        <p className="mb-2 text-xs text-red-600">{errorText(add.error, '追加できませんでした')}</p>
      )}
      {terms.isSuccess && items.length === 0 && (
        <p data-testid="user-terms-empty" className="text-xs text-neutral-500">
          まだ何も覚えていません。質問タブで「固有名詞をスキャン」して答えるか、ここに直接追加してください。
        </p>
      )}
      {items.length > 0 && (
        <ul>
          {items.map((item) => (
            // 内容が変わったら編集欄の初期値も作り直す
            <TermRow key={`${item.id}:${item.updated_at}`} item={item} enabled={enabled} />
          ))}
        </ul>
      )}
      {overflow && (
        <p className="mt-2 text-xs text-neutral-500">
          文字起こしAIに一度に渡せる量には上限があるため、上にある語(よく答えた語・最近の語)から順に使います。
        </p>
      )}
    </section>
  )
}
