/**
 * 設定フォームの保存バー。
 *
 * 設定は即時保存せず下書きに溜め、このバーから明示的に保存する。
 * 「変更したのに反映されたか分からない」状態を作らないための画面。
 */
import { Button } from '../ui'

export function SaveBar({
  dirty,
  saving,
  saved,
  error,
  onSave,
  onDiscard,
  testId = 'settings-save',
}: {
  dirty: boolean
  saving: boolean
  /** 直近の保存が成功しているか(未保存の変更が無いときだけ表示する) */
  saved: boolean
  error: unknown
  onSave: () => void
  onDiscard: () => void
  testId?: string
}) {
  return (
    <div
      data-testid={`${testId}-bar`}
      className="sticky top-0 z-10 -mx-1 mb-2 flex items-center gap-2 border-b border-neutral-200 bg-white px-1 py-2 dark:border-neutral-800 dark:bg-neutral-950"
    >
      <span
        data-testid={`${testId}-status`}
        className={`text-xs ${
          dirty
            ? 'font-medium text-amber-600 dark:text-amber-400'
            : saved
              ? 'text-emerald-600 dark:text-emerald-400'
              : 'text-neutral-500'
        }`}
      >
        {saving
          ? '保存中...'
          : dirty
            ? '未保存の変更があります'
            : saved
              ? '保存しました'
              : '変更はありません'}
      </span>
      <span className="ml-auto" />
      {dirty && (
        <Button
          type="button"
          variant="ghost"
          onClick={onDiscard}
          disabled={saving}
          data-testid={`${testId}-discard`}
        >
          破棄
        </Button>
      )}
      <Button data-testid={testId} type="button" onClick={onSave} disabled={!dirty || saving}>
        保存
      </Button>
      {error != null && (
        <p className="text-xs text-red-600">保存に失敗しました: {String(error)}</p>
      )}
    </div>
  )
}
