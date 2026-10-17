/**
 * 全体の設定(#/settings)。ホームのヘッダーの「全体の設定」から開く。
 *
 * 以前は編集画面の「設定」タブにしか無く、文字起こしが終わって「開く」が押せるまで
 * 設定を見直せなかった(v2.0の初心者評価)。フォームは編集画面のタブと同じものを使う。
 */
import { SettingsForm } from '../components/settings/SettingsForm'
import { BackIcon } from '../components/icons'
import { Button } from '../components/ui'
import { navigate } from '../hooks/useHashRoute'

/**
 * 「これは全体の設定」と分かる見出し。プロジェクトの設定(ホームの各プロジェクトの
 * 「設定」)との関係もここで伝える。全体の設定ページと編集画面の設定タブで共有する
 */
export function GlobalSettingsHeading({
  className = '',
  as: Tag = 'h2',
}: {
  className?: string
  as?: 'h1' | 'h2'
}) {
  return (
    <div data-testid="global-settings-heading" className={className}>
      <Tag className="text-base font-semibold">全体の設定(すべてのプロジェクト共通)</Tag>
      <p className="mt-1 text-xs text-neutral-500">
        プロジェクトごとに変えたい項目は、ホームの各プロジェクトの「設定」で上書きできます。
        上書きしていない項目は、ここでの変更に従います。
      </p>
    </div>
  )
}

export function GlobalSettings() {
  return (
    <main className="mx-auto max-w-3xl px-6 pb-16 pt-8">
      <header className="mb-2 flex items-center gap-3">
        <Button
          data-testid="settings-back"
          variant="ghost"
          className="flex shrink-0 items-center gap-1"
          onClick={() => navigate({ page: 'home' })}
        >
          <BackIcon />
          プロジェクト一覧
        </Button>
      </header>
      <GlobalSettingsHeading as="h1" className="px-4" />
      <SettingsForm />
    </main>
  )
}
